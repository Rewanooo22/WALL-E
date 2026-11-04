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
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from wall_e.models import (
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


def _parse_contracted_scope(raw: Any, issues: list[ManifestIssue]) -> ContractedScope | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("disciplines"), list):
        _issue(issues, "contracted_scope", "must be an object with a 'disciplines' list",
               "contracted execution scope treated as not declared")
        return None
    disciplines: list[Discipline] = []
    for d in raw["disciplines"]:
        try:
            disc = Discipline(d)
        except ValueError:
            _issue(issues, "contracted_scope.disciplines", f"unknown discipline {d!r}", "ignored")
            continue
        if disc not in disciplines:
            disciplines.append(disc)
    basis = raw.get("basis") or []
    if not isinstance(basis, list) or not all(isinstance(b, dict) for b in basis):
        _issue(issues, "contracted_scope.basis", "must be a list of objects", "basis ignored")
        basis = []
    notes = raw.get("notes")
    return ContractedScope(
        declared_by=str(raw.get("declared_by") or "user"),
        disciplines=tuple(disciplines),
        basis=tuple(basis),
        notes=notes if isinstance(notes, str) else None,
    )


def _parse_files(raw: Any, issues: list[ManifestIssue]) -> tuple[ManifestFileEntry, ...]:
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
        try:
            cls = Classification(item.get("classification"))
        except ValueError:
            _issue(issues, fld, f"invalid classification {item.get('classification')!r}",
                   "entry ignored; default classification applies")
            continue
        if norm in entries:
            _issue(issues, fld, f"duplicate entry for {norm!r}", "later entry ignored")
            continue
        entries[norm] = ManifestFileEntry(path=norm, classification=cls)
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
    if not path.is_file() or path.is_symlink():
        raise ManifestError(f"{MANIFEST_NAME} not found (or is a symlink) in {project_dir}")
    data = path.read_bytes()
    if len(data) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"{MANIFEST_NAME} exceeds {MAX_MANIFEST_BYTES} bytes")
    sha = hashlib.sha256(data).hexdigest()
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{MANIFEST_NAME} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{MANIFEST_NAME} must contain a JSON object")

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
        _issue(issues, "contracted_scope", "not declared",
               "contracted execution scope reported as not declared; MI-08 not evaluated")

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

    files = _parse_files(raw.get("files"), issues)
    conventions = _parse_conventions(raw.get("conventions"), issues)

    try:
        manifest = ProjectManifest(
            schema_version=str(raw.get("schema_version")),
            project_id=str(raw.get("project_id", "")),
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


def scan_project(project_dir: Path, limits: Limits = Limits()) -> ProjectScan:
    """Validate the manifest and build the coverage list for one project.

    Only paths under project_dir are listed or opened (project isolation).
    """
    root = Path(project_dir).resolve(strict=True)
    if not root.is_dir():
        raise ManifestError(f"{project_dir} is not a directory")
    manifest, manifest_sha = load_manifest(root)
    issues = list(manifest.issues)
    by_path = {e.path: e for e in manifest.files}

    records: list[FileRecord] = []
    seen_paths: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        # Symlinked directories are listed but never traversed.
        for d in sorted(dirnames):
            p = current / d
            if p.is_symlink():
                rel = p.relative_to(root).as_posix()
                records.append(_record(rel, FileType.OTHER, FileStatus.REJECTED_PATH, manifest, by_path,
                                       reason="symbolic link to a directory; not traversed"))
                seen_paths.add(rel)
        dirnames[:] = sorted(d for d in dirnames if not (current / d).is_symlink())

        for name in sorted(filenames):
            p = current / name
            rel = p.relative_to(root).as_posix()
            if rel == MANIFEST_NAME:
                continue
            seen_paths.add(rel)
            records.append(_classify_file(p, rel, root, manifest, by_path, limits))

    for entry in manifest.files:
        if entry.path not in seen_paths:
            issues.append(ManifestIssue(field=f"files:{entry.path}", problem="listed file not found",
                                        effect="entry ignored"))

    records.sort(key=lambda r: r.rel_path)
    records = _mark_duplicates(records)
    manifest = manifest.model_copy(update={"issues": tuple(issues)})
    return ProjectScan(root=root, manifest=manifest, manifest_sha256=manifest_sha, files=records)


def _record(rel: str, ftype: FileType, status: FileStatus, manifest: ProjectManifest,
            by_path: dict[str, ManifestFileEntry], **kw: Any) -> FileRecord:
    entry = by_path.get(rel)
    if entry is not None:
        cls, src = entry.classification, ClassificationSource.MANIFEST_FILE_ENTRY
    else:
        cls, src = manifest.default_classification, manifest.default_classification_source
    return FileRecord(rel_path=rel, file_type=ftype, status=status, classification=cls,
                      classification_source=src, **kw)


def _classify_file(p: Path, rel: str, root: Path, manifest: ProjectManifest,
                   by_path: dict[str, ManifestFileEntry], limits: Limits) -> FileRecord:
    ftype = _EXT.get(p.suffix.lower(), FileType.OTHER)

    if p.is_symlink():
        target = p.resolve()
        if not _is_within(target, root):
            return _record(rel, ftype, FileStatus.REJECTED_PATH, manifest, by_path,
                           reason="symbolic link resolves outside the project root")
        if not target.is_file():
            return _record(rel, ftype, FileStatus.REJECTED_PATH, manifest, by_path,
                           reason="symbolic link does not resolve to a regular file")
        # An internal link is never the primary copy, whatever the path order.
        target_rel = target.relative_to(root).as_posix()
        return _record(rel, ftype, FileStatus.DUPLICATE, manifest, by_path,
                       duplicate_of=target_rel, reason=f"symbolic link to {target_rel}")
    elif not p.is_file():
        return _record(rel, ftype, FileStatus.REJECTED_PATH, manifest, by_path,
                       reason="not a regular file")

    size = p.stat().st_size
    if size > limits.max_file_bytes:
        return _record(rel, ftype, FileStatus.LIMIT_EXCEEDED, manifest, by_path, size_bytes=size,
                       reason=f"file size {size} exceeds limit {limits.max_file_bytes}")

    sha = _sha256_file(p)
    if ftype is FileType.OTHER:
        return _record(rel, ftype, FileStatus.UNSUPPORTED, manifest, by_path, size_bytes=size, sha256=sha,
                       reason=f"unsupported file type {p.suffix or '(no extension)'!r}")
    with p.open("rb") as fh:
        head = fh.read(8)
    if not head.startswith(_MAGIC[ftype]):
        return _record(rel, ftype, FileStatus.UNSUPPORTED, manifest, by_path, size_bytes=size, sha256=sha,
                       reason=f"content does not match the {ftype.value} file signature")
    return _record(rel, ftype, FileStatus.DISCOVERED, manifest, by_path, size_bytes=size, sha256=sha)


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
