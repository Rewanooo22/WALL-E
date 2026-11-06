"""Project loading: manifest validation, file discovery, hashing, classification.

Spec references: §4.1 (supported files), §4.2 (manifest), §7.7 (coverage),
§12 step 1, §14.1 (path validation, pre-parse limits).

Design rules:
- Fatal manifest problems (missing or unparsable manifest, invalid project_id,
  unsupported schema) raise ManifestError. Everything else becomes a
  ManifestIssue, and the dependent feature degrades to UNKNOWN or "not evaluated".
- No file content is parsed here, only read to hash it and check its magic
  bytes. Parsing happens in isolated workers (M3).
- Output is deterministic: files are sorted by relative POSIX path.
- Containment is checked on resolved paths, so symlinks, Windows junctions and
  other reparse points that leave the project root are rejected and never
  traversed or hashed. A hard link to a file outside the project cannot be
  detected this way (stated limitation).
- Manifest entries are matched to files by exact path, then by the filesystem's own
  resolution of the entry's spelling (parent directory and file identity from lstat
  metadata, via extended-length paths on Windows); names are never case-folded (N-1, F-1).
  Classifications are path-specific: never transferred between hard-link names (F-3).
  See _apply_declarations for the tie-break and the fallback when identity is unavailable.
- A filesystem error on one entry is recorded as UNREADABLE (error class only, no
  paths or stack traces) and the scan continues (INV-07).
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from wall_e.models import (
    CLASSIFICATION_RESTRICTIVENESS,
    BoqColumns,
    Classification,
    ClassificationSource,
    ContractedScope,
    Conventions,
    DeliveryModel,
    Discipline,
    FileRecord,
    FileStatus,
    FileType,
    ManifestFileEntry,
    ManifestIssue,
    ProjectManifest,
)

MANIFEST_NAME = "project.json"
MAX_MANIFEST_BYTES = 1_000_000

_KNOWN_TOP_LEVEL = {
    "schema_version", "project_id", "title", "description", "delivery_model",
    "delivery_model_notes", "contracted_scope", "default_classification", "files", "conventions",
}
_KNOWN_CONVENTIONS = {
    "document_number_pattern", "discipline_codes", "tag_pattern", "revision_sequence",
    "execution_issue_statuses", "boq_columns",
}


class ManifestError(Exception):
    """The manifest cannot be used at all; the run must stop."""


@dataclass(frozen=True)
class Limits:
    """Pre-parse limits (spec §14.1). Defaults are WALL-E defaults, not company values."""

    max_file_bytes: int = 200 * 1024 * 1024


@dataclass
class ProjectScan:
    root: Path
    manifest: ProjectManifest
    manifest_sha256: str
    files: list[FileRecord] = field(default_factory=list)


# --------------------------------------------------------------------------- manifest


def _issue(issues: list[ManifestIssue], fld: str, problem: str, effect: str) -> None:
    issues.append(ManifestIssue(field=fld, problem=problem, effect=effect))


def _regex_or_none(value: Any, fld: str, issues: list[ManifestIssue]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _issue(issues, fld, "not a string", "convention treated as not declared")
        return None
    try:
        re.compile(value)
    except re.error as exc:
        _issue(issues, fld, f"invalid regular expression: {exc}", "convention treated as not declared")
        return None
    return value


def _str_list_or_none(value: Any, fld: str, issues: list[ManifestIssue]) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        _issue(issues, fld, "must be a list of non-empty strings", "convention treated as not declared")
        return None
    return tuple(value)


def _parse_conventions(raw: Any, issues: list[ManifestIssue]) -> Conventions:
    if raw is None:
        return Conventions()
    if not isinstance(raw, dict):
        _issue(issues, "conventions", "not an object", "all conventions treated as not declared")
        return Conventions()
    for key in sorted(set(raw) - _KNOWN_CONVENTIONS):
        _issue(issues, f"conventions.{key}", "unknown field", "ignored")

    codes = None
    raw_codes = raw.get("discipline_codes")
    if raw_codes is not None:
        if not isinstance(raw_codes, dict):
            _issue(issues, "conventions.discipline_codes", "not an object", "convention treated as not declared")
        else:
            parsed: dict[str, Discipline] = {}
            for code, disc in raw_codes.items():
                try:
                    parsed[str(code)] = Discipline(disc)
                except ValueError:
                    _issue(issues, f"conventions.discipline_codes.{code}",
                           f"unknown discipline {disc!r}", "this code is ignored")
            codes = parsed or None

    boq = None
    raw_boq = raw.get("boq_columns")
    if raw_boq is not None:
        try:
            boq = BoqColumns.model_validate(raw_boq)
        except ValidationError:
            _issue(issues, "conventions.boq_columns",
                   "must have string fields item, description, unit, quantity",
                   "default BOQ header list will be used")

    return Conventions(
        document_number_pattern=_regex_or_none(raw.get("document_number_pattern"),
                                               "conventions.document_number_pattern", issues),
        discipline_codes=codes,
        tag_pattern=_regex_or_none(raw.get("tag_pattern"), "conventions.tag_pattern", issues),
        revision_sequence=_str_list_or_none(raw.get("revision_sequence"),
                                            "conventions.revision_sequence", issues),
        execution_issue_statuses=_str_list_or_none(raw.get("execution_issue_statuses"),
                                                   "conventions.execution_issue_statuses", issues),
        boq_columns=boq,
    )


_NOT_DECLARED = "contracted execution scope reported as not declared; MI-08 not evaluated"


def _parse_contracted_scope(raw: Any, issues: list[ManifestIssue]) -> ContractedScope | None:
    """None = NOT_DECLARED. A ContractedScope with zero disciplines = DECLARED, empty.

    - disciplines missing or null -> NOT_DECLARED
    - disciplines == []           -> DECLARED with zero disciplines
    - non-empty with ANY invalid entry -> NOT_DECLARED (issue lists the invalid entries);
      a valid subset is never silently accepted
    - declared_by missing or not exactly "user" -> NOT_DECLARED (with issue)
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        _issue(issues, "contracted_scope", "must be an object", _NOT_DECLARED)
        return None
    if raw.get("declared_by") != "user":
        problem = ("missing; must be exactly 'user'" if "declared_by" not in raw
                   else f"must be exactly 'user', got {raw['declared_by']!r}")
        _issue(issues, "contracted_scope.declared_by", problem, _NOT_DECLARED)
        return None
    raw_disc = raw.get("disciplines")
    if raw_disc is None:
        _issue(issues, "contracted_scope.disciplines", "not declared", _NOT_DECLARED)
        return None
    if not isinstance(raw_disc, list):
        _issue(issues, "contracted_scope.disciplines", "must be a list", _NOT_DECLARED)
        return None
    disciplines: list[Discipline] = []
    invalid: list[Any] = []
    for d in raw_disc:
        try:
            disc = Discipline(d)
        except ValueError:
            invalid.append(d)
            continue
        if disc not in disciplines:
            disciplines.append(disc)
    if invalid:
        _issue(issues, "contracted_scope.disciplines",
               f"invalid disciplines {invalid!r} (allowed: {[x.value for x in Discipline]})",
               _NOT_DECLARED)
        return None
    basis = raw.get("basis") or []
    if not isinstance(basis, list) or not all(isinstance(b, dict) for b in basis):
        _issue(issues, "contracted_scope.basis", "must be a list of objects", "basis ignored")
        basis = []
    notes = raw.get("notes")
    return ContractedScope(
        declared_by="user",
        disciplines=tuple(disciplines),
        basis=tuple(basis),
        notes=notes if isinstance(notes, str) else None,
    )


# F-C: duplicate entries for one path with the SAME classification keep the source with the
# highest rank: an explicit valid label, then a fail-safe for an invalid label, then the
# default. A manifest has only one of the two default sources, so ties are identical entries.
_SOURCE_TIE_RANK = {
    ClassificationSource.MANIFEST_FILE_ENTRY: 3,
    ClassificationSource.FAIL_SAFE_INVALID_LABEL: 2,
    ClassificationSource.MANIFEST_DEFAULT: 1,
    ClassificationSource.BUILT_IN_DEFAULT: 1,
}


def _parse_files(raw: Any, issues: list[ManifestIssue], default_cls: Classification,
                 default_src: ClassificationSource) -> tuple[ManifestFileEntry, ...]:
    """Per-file classifications (spec §4.2, FR-SEC-001).

    - "classification" key missing -> unlabelled: the manifest default applies.
    - "classification" present but invalid (incl. null) -> confidential, with an issue.
    - Several entries with the same (normalised) path -> the most restrictive wins; with
      equal classifications the source is chosen by _SOURCE_TIE_RANK (F-C). The result
      never depends on the order of entries in the manifest.
    Entries spelled differently that the filesystem resolves to the same discovered path
    (e.g. case variants on a case-insensitive filesystem) are matched later, during the
    scan (_apply_declarations); no name folding is attempted here. Hard-link names are
    different paths and keep their own classifications (F-3).
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        _issue(issues, "files", "not a list", "per-file classifications ignored; default applies")
        return ()
    entries: dict[str, ManifestFileEntry] = {}
    for i, item in enumerate(raw):
        fld = f"files[{i}]"
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            _issue(issues, fld, "entry must be an object with a string 'path'", "entry ignored")
            continue
        norm = _normalise_rel_path(item["path"])
        if norm is None:
            _issue(issues, fld, f"path {item['path']!r} is absolute or escapes the project root",
                   "entry ignored")
            continue
        if "classification" not in item:
            entry = ManifestFileEntry(path=norm, classification=default_cls, classification_source=default_src)
        else:
            # Fail-safe (FR-SEC-001): an explicit invalid label never falls back to a
            # less restrictive default; it is treated as confidential.
            try:
                entry = ManifestFileEntry(path=norm, classification=Classification(item["classification"]))
            except ValueError:
                _issue(issues, fld, f"invalid classification {item['classification']!r}",
                       "treated as confidential")
                entry = ManifestFileEntry(path=norm, classification=Classification.CONFIDENTIAL,
                                          classification_source=ClassificationSource.FAIL_SAFE_INVALID_LABEL)
        prev = entries.get(norm)
        if prev is None:
            entries[norm] = entry
            continue
        if prev.classification is entry.classification:
            # F-C: which classification_source is kept must not depend on manifest order.
            entries[norm] = max(prev, entry, key=lambda e: _SOURCE_TIE_RANK[e.classification_source])
            _issue(issues, fld, f"duplicate entry for {norm!r}",
                   "same classification; merged (source chosen by fixed rank, not manifest order)")
            continue
        keep = max(prev, entry, key=lambda e: CLASSIFICATION_RESTRICTIVENESS[e.classification])
        _issue(issues, fld, f"conflicting duplicate entry for {norm!r}",
               f"most restrictive classification applies: {keep.classification.value}")
        entries[norm] = keep
    return tuple(entries[k] for k in sorted(entries))


def _normalise_rel_path(p: str) -> str | None:
    """Return a clean relative POSIX path, or None if absolute or escaping."""
    if not p or "\\" in p or p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return None
    parts = [x for x in PurePosixPath(p).parts if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts):
        return None
    return "/".join(parts)


def load_manifest(project_dir: Path) -> tuple[ProjectManifest, str]:
    """Load and validate project.json. Returns (manifest, sha256 of manifest bytes)."""
    path = Path(project_dir) / MANIFEST_NAME
    try:
        if not path.is_file() or path.is_symlink():
            raise ManifestError(f"{MANIFEST_NAME} not found (or is a symlink) in {project_dir}")
        data = path.read_bytes()
    except OSError as exc:  # L-4: explicit ManifestError; error class only, no path
        raise ManifestError(f"{MANIFEST_NAME} cannot be read ({_fs_error_reason(exc, 'read failed')})") from exc
    if len(data) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"{MANIFEST_NAME} exceeds {MAX_MANIFEST_BYTES} bytes")
    sha = hashlib.sha256(data).hexdigest()
    try:
        # utf-8-sig: accept a UTF-8 BOM (written by e.g. Windows PowerShell 5.1 Out-File).
        raw = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{MANIFEST_NAME} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{MANIFEST_NAME} must contain a JSON object")
    # Required identity fields must be JSON strings; no coercion (null -> "None", 1.0 -> "1.0").
    for key in ("schema_version", "project_id"):
        if not isinstance(raw.get(key), str):
            got = "missing" if key not in raw else type(raw[key]).__name__
            raise ManifestError(f"{MANIFEST_NAME} is invalid: {key} must be a string (got {got})")

    issues: list[ManifestIssue] = []
    for key in sorted(set(raw) - _KNOWN_TOP_LEVEL):
        _issue(issues, key, "unknown field", "ignored")

    # delivery model: absent or invalid -> UNKNOWN (spec §4.2, §5)
    dm_raw = raw.get("delivery_model")
    delivery_model = None
    if dm_raw is None:
        _issue(issues, "delivery_model", "not declared", "delivery model reported as UNKNOWN")
    else:
        try:
            delivery_model = DeliveryModel(dm_raw)
        except ValueError:
            _issue(issues, "delivery_model", f"invalid value {dm_raw!r}",
                   "delivery model reported as UNKNOWN")
    dm_notes = raw.get("delivery_model_notes")
    dm_notes = dm_notes if isinstance(dm_notes, str) and dm_notes.strip() else None
    if delivery_model is DeliveryModel.HYBRID and dm_notes is None:
        _issue(issues, "delivery_model_notes", "HYBRID declared without notes",
               "design-responsibility split reported as UNKNOWN")

    contracted = _parse_contracted_scope(raw.get("contracted_scope"), issues)
    if contracted is None and raw.get("contracted_scope") is None:
        _issue(issues, "contracted_scope", "not declared", _NOT_DECLARED)

    if "default_classification" in raw:
        try:
            default_cls = Classification(raw["default_classification"])
            default_src = ClassificationSource.MANIFEST_DEFAULT
        except ValueError:
            _issue(issues, "default_classification", f"invalid value {raw['default_classification']!r}",
                   "built-in default 'confidential' applies")
            default_cls, default_src = Classification.CONFIDENTIAL, ClassificationSource.BUILT_IN_DEFAULT
    else:
        default_cls, default_src = Classification.CONFIDENTIAL, ClassificationSource.BUILT_IN_DEFAULT

    def _opt_str(key: str) -> str | None:
        v = raw.get(key)
        if v is not None and not isinstance(v, str):
            _issue(issues, key, "not a string", "ignored")
            return None
        return v

    files = _parse_files(raw.get("files"), issues, default_cls, default_src)
    conventions = _parse_conventions(raw.get("conventions"), issues)

    try:
        manifest = ProjectManifest(
            schema_version=raw["schema_version"],
            project_id=raw["project_id"],
            title=_opt_str("title"),
            description=_opt_str("description"),
            delivery_model=delivery_model,
            delivery_model_raw=dm_raw if isinstance(dm_raw, str) else (None if dm_raw is None else str(dm_raw)),
            delivery_model_notes=dm_notes,
            contracted_scope=contracted,
            default_classification=default_cls,
            default_classification_source=default_src,
            files=files,
            conventions=conventions,
            issues=tuple(issues),
        )
    except ValidationError as exc:
        raise ManifestError(f"{MANIFEST_NAME} is invalid: {exc.errors()[0]['msg']}") from exc
    return manifest, sha


# --------------------------------------------------------------------------- discovery

_MAGIC = {FileType.PDF: b"%PDF-", FileType.XLSX: b"PK\x03\x04"}
_EXT = {".pdf": FileType.PDF, ".xlsx": FileType.XLSX}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _fs_error_reason(exc: BaseException, what: str) -> str:
    """Error class (and errno name) only: no paths, no messages, no stack traces."""
    code = errno.errorcode.get(exc.errno) if isinstance(exc, OSError) and exc.errno else None
    return f"{what}: {type(exc).__name__}" + (f" ({code})" if code else "")


_FS_ERRORS = (OSError, RuntimeError)  # RuntimeError: symlink loop on some Python versions
_LOOKUP_ERRORS = (*_FS_ERRORS, ValueError)  # ValueError: e.g. NUL character in a manifest path

FileId = tuple[int, int]  # (st_dev, st_ino)

# Manifest path components never looked up on Windows: ':' (drive or alternate data
# stream syntax) and device names, which the Win32 layer maps to devices, not files.
WINDOWS_PATH_RULES = os.name == "nt"  # module-level so tests can enable it on any OS
_WINDOWS_DEVICE_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
    | {f"{p}{i}" for p in ("COM", "LPT") for i in (*"0123456789", "¹", "²", "³")})


class _IdentityUnavailable(Exception):
    """No safe file-identity lookup is possible for a manifest path."""


_EXTENDED_PATHS = os.name == "nt"
_XP = "\\\\?\\"  # the Windows extended-length path prefix: \\?\


def _os_path(p: Path) -> str:
    """The path string used for metadata lookups. On Windows an extended-length path
    (\\\\?\\...), so the Win32 layer does not strip trailing dots/spaces or map device names
    (F-1): 'a.pdf.' is then looked up as itself, not as 'a.pdf'. NTFS-level behaviour
    (case-insensitivity, case-sensitive directories, 8.3 short names) is unchanged.
    Only used for lookups; reported paths are always the discovered relative paths."""
    s = str(p)
    if not _EXTENDED_PATHS or s.startswith(_XP):
        return s
    if s.startswith("\\\\"):
        return _XP + "UNC\\" + s[2:]
    return _XP + s


def _file_id(path: Path) -> FileId | None:
    """File identity from lstat metadata (links are not followed; nothing is opened for
    reading). None when the filesystem reports no file ID (st_ino == 0)."""
    st = os.lstat(_os_path(path))
    return (st.st_dev, st.st_ino) if st.st_ino else None


def _resolve_declared(root: Path, rel: str, dir_ids: dict[str, FileId]) -> tuple[FileId, FileId, int]:
    """(parent directory identity, entry identity, link count) of the directory entry a
    manifest path names, from lstat metadata only.

    The filesystem's own name resolution decides which entry a path names (NTFS case
    rules, case-sensitive directories, 8.3 names); no case folding is done here. Every
    directory component must be one this scan traversed (matched by identity), so a
    lookup never passes through a link, junction, rejected or unlisted directory, and
    never touches anything outside the project.

    Raises FileNotFoundError if nothing exists there, _IdentityUnavailable when no safe
    lookup or no file ID is available, other _LOOKUP_ERRORS on failure."""
    parts = rel.split("/")
    if WINDOWS_PATH_RULES and any(
            ":" in x or x.split(".", 1)[0].rstrip(" ").upper() in _WINDOWS_DEVICE_STEMS for x in parts):
        raise _IdentityUnavailable("path contains ':' or a Windows device name; other spellings not checked")
    walked = set(dir_ids.values())
    parent_id = dir_ids.get("")
    if parent_id is None:
        raise _IdentityUnavailable("the project directory reports no file identity; other spellings not checked")
    cur = root
    for i, part in enumerate(parts):
        nxt = cur / part
        if nxt.parent != cur:
            raise _IdentityUnavailable("path component is not a plain name; other spellings not checked")
        cur = nxt
        if i < len(parts) - 1:
            st = os.lstat(_os_path(cur))
            if not stat.S_ISDIR(st.st_mode) or not st.st_ino or (st.st_dev, st.st_ino) not in walked:
                raise _IdentityUnavailable(
                    "path passes through a directory this scan did not traverse; other spellings not checked")
            parent_id = (st.st_dev, st.st_ino)
    st = os.lstat(_os_path(cur))
    if not st.st_ino:
        raise _IdentityUnavailable(
            "a file exists under this spelling but the filesystem reports no file identity, "
            "so it could not be matched to a discovered path")
    return parent_id, (st.st_dev, st.st_ino), st.st_nlink


def _on_disk_rel(root: Path, rel: str) -> str | None:
    """Windows only: the exact on-disk relative path of the directory entry a spelling
    names (final-path query; for a hard link it returns the link that was named).
    Only called after _resolve_declared succeeded for the same path. None for links and
    reparse points (the query would follow them) and when the answer is not under root."""
    if not _EXTENDED_PATHS:
        return None
    target = _os_path(root.joinpath(*rel.split("/")))
    st = os.lstat(target)
    if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return None
    final = os.path.realpath(target, strict=True)
    prefix = _os_path(root).rstrip("\\") + "\\"
    if not final.startswith(prefix):
        return None
    return final[len(prefix):].replace("\\", "/")


def _dir_problem(p: Path, root: Path) -> tuple[FileStatus, str] | None:
    """None if p is an ordinary directory inside root that may be traversed."""
    try:
        is_link = p.is_symlink()
        resolved = p.resolve(strict=True)
    except FileNotFoundError as exc:
        # L-5: the entry itself still exists (lexists) -> a link whose target is missing
        # (incl. a junction, which is_symlink() does not report); otherwise the
        # directory vanished after listing.
        if os.path.lexists(p):
            return FileStatus.REJECTED_PATH, "link does not resolve to an existing target; not traversed"
        return FileStatus.UNREADABLE, _fs_error_reason(exc, "directory could not be resolved")
    except _FS_ERRORS as exc:
        return FileStatus.UNREADABLE, _fs_error_reason(exc, "directory could not be resolved")
    if not is_link and resolved == p:
        return None
    if not _is_within(resolved, root):
        return FileStatus.REJECTED_PATH, "link or reparse point resolves outside the project root; not traversed"
    return FileStatus.REJECTED_PATH, "link or reparse point to a directory; not traversed"


def scan_project(project_dir: Path, limits: Limits = Limits()) -> ProjectScan:
    """Validate the manifest and build the coverage list for one project.

    Only paths under project_dir are listed or opened (project isolation).
    """
    root = Path(project_dir).resolve(strict=True)
    if not root.is_dir():
        raise ManifestError(f"{project_dir} is not a directory")
    manifest, manifest_sha = load_manifest(root)
    issues = list(manifest.issues)

    records: list[FileRecord] = []
    record_ids: dict[str, FileId] = {}  # rel_path -> identity of the entry itself (lstat)
    dir_ids: dict[str, FileId] = {}     # rel path ("" = root) -> identity, traversed directories only

    def add(rec: FileRecord, p: Path) -> None:
        records.append(rec)
        try:
            fid = _file_id(p)
        except _LOOKUP_ERRORS:
            fid = None
        if fid is not None:
            record_ids[rec.rel_path] = fid

    def on_walk_error(exc: OSError) -> None:
        # A directory that cannot be listed is recorded, never dropped silently (INV-07).
        try:
            rel = Path(exc.filename).relative_to(root).as_posix() if exc.filename else None
        except ValueError:
            rel = None
        if rel is None or rel == ".":
            raise ManifestError(
                f"project directory cannot be listed ({_fs_error_reason(exc, 'listing failed')})") from exc
        if all(r.rel_path != rel for r in records):
            add(_record(rel, FileType.OTHER, FileStatus.UNREADABLE, manifest,
                        reason=_fs_error_reason(exc, "directory could not be listed")), root / rel)

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_walk_error, followlinks=False):
        current = Path(dirpath)
        try:
            if (fid := _file_id(current)) is not None:
                cur_rel = current.relative_to(root).as_posix()
                dir_ids["" if cur_rel == "." else cur_rel] = fid
        except _LOOKUP_ERRORS:
            pass  # identity lookups below this directory are then refused (fail closed)
        # Links, junctions and reparse points are listed but never traversed.
        traverse = []
        for d in sorted(dirnames):
            p = current / d
            problem = _dir_problem(p, root)
            if problem is None:
                traverse.append(d)
                continue
            rel = p.relative_to(root).as_posix()
            add(_record(rel, FileType.OTHER, problem[0], manifest, reason=problem[1]), p)
        dirnames[:] = traverse

        for name in sorted(filenames):
            p = current / name
            rel = p.relative_to(root).as_posix()
            if rel == MANIFEST_NAME:
                continue
            add(_classify_file(p, rel, root, manifest, limits), p)

    records, match_issues = _apply_declarations(root, records, record_ids, dir_ids, manifest)
    issues.extend(match_issues)

    records.sort(key=lambda r: r.rel_path)
    records = _mark_duplicates(records)
    manifest = manifest.model_copy(update={"issues": tuple(issues)})
    return ProjectScan(root=root, manifest=manifest, manifest_sha256=manifest_sha, files=records)


def _apply_declarations(root: Path, records: list[FileRecord], record_ids: dict[str, FileId],
                        dir_ids: dict[str, FileId], manifest: ProjectManifest,
                        ) -> tuple[list[FileRecord], list[ManifestIssue]]:
    """Match manifest entries to discovered paths and apply classifications.

    Classifications are path-specific (F-3): an entry applies to exactly one discovered
    path, never to other names of the same file (hard links).
    1. Exact path: an entry whose path equals a discovered rel_path applies to it.
    2. Other spellings (N-1): the filesystem resolves the entry's path (lstat metadata
       only, see _resolve_declared) to a directory entry; the entry applies to the
       discovered path with the same parent directory identity and the same file
       identity, once confirmed to be the very entry the spelling names (F-A): its exact
       on-disk name (Windows, _on_disk_rel) must be that path; where no on-disk name is
       available, it must be the only candidate and the file's only name (link count 1).
       Otherwise (e.g. hard links, including an undiscovered one such as the manifest)
       the entry is not applied (issue).
    3. Several entries applying to one path -> the most restrictive classification.
       Tie-break (deterministic): among equally restrictive entries the exact-path entry
       supplies classification_source; otherwise the first in manifest path order
       (entries are sorted by path, Unicode code point order).
    A discovered path with no entry applying to it keeps default_classification, whatever
    other names of the same file are declared as. Hard-link names with different
    classifications are reported, not merged.
    Fallback: where identity is unavailable (st_ino == 0, lookup refused or failed),
    only exact path matching applies and an unmatched entry is reported as a
    "listed file not found" issue; the discovered file then keeps the default. No
    lowering happens without an issue saying the entry was not applied.
    """
    issues: list[ManifestIssue] = []
    rec_paths = {r.rel_path for r in records}
    by_slot: dict[tuple[FileId, FileId], list[str]] = {}  # (parent id, file id) -> discovered paths
    for rel, fid in sorted(record_ids.items()):
        parent_id = dir_ids.get(rel.rsplit("/", 1)[0] if "/" in rel else "")
        if parent_id is not None:
            by_slot.setdefault((parent_id, fid), []).append(rel)

    applying: dict[str, list[ManifestFileEntry]] = {}
    for entry in manifest.files:  # sorted by path, unique paths
        target = entry.path if entry.path in rec_paths else None
        problem = "listed file not found"
        if target is None:
            try:
                parent_id, fid, nlink = _resolve_declared(root, entry.path, dir_ids)
                candidates = by_slot.get((parent_id, fid), [])
                # F-A: a candidate is only accepted once it is confirmed to be the very entry
                # this spelling names: by its exact on-disk name (Windows), or, where no name
                # is available, by being the file's only name (link count 1). Otherwise another
                # name of the same file (a hard link, possibly undiscovered such as the
                # manifest) could receive this declaration.
                on_disk = _on_disk_rel(root, entry.path) if candidates else None
                if on_disk == MANIFEST_NAME:
                    problem = "listed file not found (the path names the project manifest, which is not an input)"
                elif on_disk is not None and on_disk in candidates:
                    target = on_disk
                elif on_disk is None and len(candidates) == 1 and nlink == 1:
                    target = candidates[0]
                elif candidates:
                    problem = (f"listed file not found at this exact path (it names a file that also has "
                               f"the discovered name(s) {candidates!r}, but could not be confirmed as any "
                               f"of them; on-disk name: {on_disk!r}, link count: {nlink})")
                else:
                    problem = "listed file not found (the path names an entry that is not a discovered file)"
            except (FileNotFoundError, NotADirectoryError):
                pass
            except _IdentityUnavailable as exc:
                problem = f"listed file not found at this exact path ({exc})"
            except _LOOKUP_ERRORS as exc:
                problem = f"listed file not found at this exact path ({_fs_error_reason(exc, 'lookup failed')})"
        if target is None:
            issues.append(ManifestIssue(field=f"files:{entry.path}", problem=problem, effect="entry ignored"))
            continue
        if target != entry.path:
            issues.append(ManifestIssue(
                field=f"files:{entry.path}",
                problem=f"names discovered path {target!r} under another spelling (resolved by the filesystem)",
                effect=f"classification applied to {target!r}"))
        applying.setdefault(target, []).append(entry)

    out: list[FileRecord] = []
    for r in records:
        entries = applying.get(r.rel_path)
        if not entries:
            out.append(r)  # default classification, set by _record
            continue
        # Most restrictive wins; tie-break documented above (max keeps the first maximum).
        keep = max(entries, key=lambda e: (CLASSIFICATION_RESTRICTIVENESS[e.classification],
                                           e.path == r.rel_path))
        if len(entries) > 1:
            conflict = len({e.classification for e in entries}) > 1
            issues.append(ManifestIssue(
                field=f"files:{r.rel_path}", problem=f"entries {[e.path for e in entries]!r} name the same path",
                effect=(f"most restrictive classification applies: {keep.classification.value}"
                        if conflict else "same classification; no conflict")))
        out.append(r.model_copy(update={"classification": keep.classification,
                                        "classification_source": keep.classification_source}))

    # Hard links: report names of one file that ended up classified differently (F-3).
    cls_by_path = {r.rel_path: r.classification for r in out}
    by_id: dict[FileId, list[str]] = {}
    for rel, fid in sorted(record_ids.items()):
        by_id.setdefault(fid, []).append(rel)
    for names in by_id.values():
        if len(names) > 1 and len({cls_by_path[n] for n in names}) > 1:
            issues.append(ManifestIssue(
                field="files", problem=f"discovered paths {names!r} are the same file (hard links) "
                                       f"but are classified differently",
                effect="classifications are path-specific; not transferred between these paths"))
    return out, issues


def _record(rel: str, ftype: FileType, status: FileStatus, manifest: ProjectManifest, **kw: Any) -> FileRecord:
    """A record with the manifest default classification; declarations are applied
    afterwards by _apply_declarations."""
    return FileRecord(rel_path=rel, file_type=ftype, status=status,
                      classification=manifest.default_classification,
                      classification_source=manifest.default_classification_source, **kw)


def _classify_file(p: Path, rel: str, root: Path, manifest: ProjectManifest, limits: Limits) -> FileRecord:
    ftype = _EXT.get(p.suffix.lower(), FileType.OTHER)
    try:
        return _classify_file_unchecked(p, rel, ftype, root, manifest, limits)
    except _FS_ERRORS as exc:
        return _record(rel, ftype, FileStatus.UNREADABLE, manifest,
                       reason=_fs_error_reason(exc, "file could not be read"))


def _classify_file_unchecked(p: Path, rel: str, ftype: FileType, root: Path, manifest: ProjectManifest,
                             limits: Limits) -> FileRecord:
    is_link = p.is_symlink()
    try:
        target = p.resolve(strict=True)
    except FileNotFoundError:
        if is_link:
            return _record(rel, ftype, FileStatus.REJECTED_PATH, manifest,
                           reason="symbolic link does not resolve to an existing target")
        raise
    if is_link or target != p:
        # Containment is decided on the resolved path; the target is never opened.
        if not _is_within(target, root):
            return _record(rel, ftype, FileStatus.REJECTED_PATH, manifest,
                           reason="link or reparse point resolves outside the project root")
        if not target.is_file():
            return _record(rel, ftype, FileStatus.REJECTED_PATH, manifest,
                           reason="link does not resolve to a regular file")
        # An internal link is never the primary copy, whatever the path order.
        target_rel = target.relative_to(root).as_posix()
        return _record(rel, ftype, FileStatus.DUPLICATE, manifest,
                       duplicate_of=target_rel, reason=f"link to {target_rel}")

    st = p.stat()
    if not stat.S_ISREG(st.st_mode):
        return _record(rel, ftype, FileStatus.REJECTED_PATH, manifest, reason="not a regular file")

    size = st.st_size
    if size > limits.max_file_bytes:
        return _record(rel, ftype, FileStatus.LIMIT_EXCEEDED, manifest, size_bytes=size,
                       reason=f"file size {size} exceeds limit {limits.max_file_bytes}")

    sha = _sha256_file(p)
    if ftype is FileType.OTHER:
        return _record(rel, ftype, FileStatus.UNSUPPORTED, manifest, size_bytes=size, sha256=sha,
                       reason=f"unsupported file type {p.suffix or '(no extension)'!r}")
    with p.open("rb") as fh:
        head = fh.read(8)
    if not head.startswith(_MAGIC[ftype]):
        return _record(rel, ftype, FileStatus.UNSUPPORTED, manifest, size_bytes=size, sha256=sha,
                       reason=f"content does not match the {ftype.value} file signature")
    return _record(rel, ftype, FileStatus.DISCOVERED, manifest, size_bytes=size, sha256=sha)


def _mark_duplicates(records: list[FileRecord]) -> list[FileRecord]:
    """Files with identical content: the first by path is primary, others DUPLICATE."""
    first: dict[str, str] = {}
    out: list[FileRecord] = []
    for r in records:
        if r.sha256 is None or r.status is not FileStatus.DISCOVERED:
            out.append(r)
            continue
        if r.sha256 in first:
            out.append(r.model_copy(update={
                "status": FileStatus.DUPLICATE, "duplicate_of": first[r.sha256],
                "reason": f"identical content to {first[r.sha256]}"}))
        else:
            first[r.sha256] = r.rel_path
            out.append(r)
    return out
