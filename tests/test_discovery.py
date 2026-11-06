"""File discovery, hashing, classification, duplicates, path safety, isolation
(spec §4.1, §7.7, §12 step 1, §14.1, INV-04, INV-07)."""

import hashlib
import os
import pathlib
import sys

import pytest

import wall_e.project as project_mod
from conftest import PDF_STUB, XLSX_STUB, dir_link_or_skip, junction_or_skip, symlink_or_skip
from wall_e.models import Classification, ClassificationSource, FileStatus, FileType
from wall_e.project import Limits, ManifestError, scan_project


_ACCESS_EVENTS = frozenset({"open", "os.scandir", "os.listdir"})


def _under(p: str, prefix: str) -> bool:
    return p == prefix or p.startswith(prefix.rstrip(os.sep) + os.sep)


def record_opens(paths_under: str):
    """Audit hook recording file opens AND directory listings (T3) whose literal OR
    resolved location is under a prefix (N-3: an access through a junction or symlink
    has a literal path inside the project but resolves outside it).
    Returns (list of (event, path), stop)."""
    opened, state = [], {"active": True, "busy": False}
    prefix_lit = os.path.normcase(os.path.abspath(paths_under))
    prefix_real = os.path.normcase(os.path.realpath(paths_under))

    def hook(event, args):
        if (not state["active"] or state["busy"] or event not in _ACCESS_EVENTS or not args
                or not isinstance(args[0], (str, bytes, os.PathLike))):
            return
        state["busy"] = True  # realpath must not re-enter the hook
        try:
            raw = os.fsdecode(args[0])
            lit = os.path.normcase(os.path.abspath(raw))
            real = os.path.normcase(os.path.realpath(raw))
            if _under(lit, prefix_lit) or _under(real, prefix_real):
                opened.append((event, real))
        finally:
            state["busy"] = False

    sys.addaudithook(hook)
    return opened, lambda: state.update(active=False)


def by_path(scan):
    return {r.rel_path: r for r in scan.files}


def test_every_file_is_listed_sorted_with_status(make_project):
    root = make_project(contents={
        "b/spec.pdf": PDF_STUB, "a/boq.xlsx": XLSX_STUB, "notes.docx": b"PK\x03\x04docx",
        "scan.png": b"\x89PNG", "old.xls": b"\xd0\xcf\x11\xe0"})
    scan = scan_project(root)
    paths = [r.rel_path for r in scan.files]
    assert paths == sorted(paths) and "project.json" not in paths
    files = by_path(scan)
    assert files["b/spec.pdf"].status is FileStatus.DISCOVERED and files["b/spec.pdf"].file_type is FileType.PDF
    assert files["a/boq.xlsx"].status is FileStatus.DISCOVERED and files["a/boq.xlsx"].file_type is FileType.XLSX
    for p in ("notes.docx", "scan.png", "old.xls"):
        assert files[p].status is FileStatus.UNSUPPORTED and files[p].reason


def test_sha256_matches_file_content(make_project):
    root = make_project(contents={"s.pdf": PDF_STUB})
    assert by_path(scan_project(root))["s.pdf"].sha256 == hashlib.sha256(PDF_STUB).hexdigest()


def test_extension_signature_mismatch_is_unsupported(make_project):
    root = make_project(contents={"fake.pdf": b"not a pdf", "fake.xlsx": PDF_STUB})
    files = by_path(scan_project(root))
    assert files["fake.pdf"].status is FileStatus.UNSUPPORTED and "signature" in files["fake.pdf"].reason
    assert files["fake.xlsx"].status is FileStatus.UNSUPPORTED


def test_size_limit(make_project):
    root = make_project(contents={"big.pdf": PDF_STUB + b"x" * 100})
    r = by_path(scan_project(root, Limits(max_file_bytes=50)))["big.pdf"]
    assert r.status is FileStatus.LIMIT_EXCEEDED and r.sha256 is None


def test_duplicates_by_content(make_project):
    root = make_project(contents={"a.pdf": PDF_STUB, "z/copy.pdf": PDF_STUB, "other.pdf": PDF_STUB + b"1"})
    files = by_path(scan_project(root))
    assert files["a.pdf"].status is FileStatus.DISCOVERED
    assert files["z/copy.pdf"].status is FileStatus.DUPLICATE and files["z/copy.pdf"].duplicate_of == "a.pdf"
    assert files["other.pdf"].status is FileStatus.DISCOVERED


def test_classification_precedence(make_project):
    root = make_project(name="cls", contents={"listed.pdf": PDF_STUB, "unlisted.pdf": PDF_STUB + b"2"},
                        files=[{"path": "listed.pdf", "classification": "synthetic"}])
    files = by_path(scan_project(root))
    assert files["listed.pdf"].classification is Classification.SYNTHETIC
    assert files["listed.pdf"].classification_source is ClassificationSource.MANIFEST_FILE_ENTRY
    assert files["unlisted.pdf"].classification is Classification.CONFIDENTIAL
    assert files["unlisted.pdf"].classification_source is ClassificationSource.BUILT_IN_DEFAULT

    root2 = make_project(name="cls2", contents={"unlisted.pdf": PDF_STUB}, default_classification="synthetic")
    r = by_path(scan_project(root2))["unlisted.pdf"]
    assert r.classification is Classification.SYNTHETIC
    assert r.classification_source is ClassificationSource.MANIFEST_DEFAULT


def test_manifest_listed_file_not_found_is_reported(make_project):
    root = make_project(name="missing", files=[{"path": "ghost.pdf", "classification": "synthetic"}])
    scan = scan_project(root)
    assert any(i.field == "files:ghost.pdf" and "not found" in i.problem for i in scan.manifest.issues)


def test_symlinks_escaping_root_are_rejected_and_dirs_not_traversed(make_project, tmp_path):
    # Skips only if symlink creation actually fails (e.g. Windows without the privilege).
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.pdf").write_bytes(PDF_STUB)
    root = make_project(contents={"real.pdf": PDF_STUB + b"r"})
    symlink_or_skip(outside / "secret.pdf", root / "link.pdf")
    symlink_or_skip(outside, root / "linkdir", is_dir=True)
    symlink_or_skip(root / "real.pdf", root / "inner_link.pdf")
    files = by_path(scan_project(root))
    assert files["link.pdf"].status is FileStatus.REJECTED_PATH and files["link.pdf"].sha256 is None
    assert files["linkdir"].status is FileStatus.REJECTED_PATH
    assert not any(p.startswith("linkdir/") for p in files)
    # The internal link sorts before its target but must never become the primary copy.
    assert files["inner_link.pdf"].status is FileStatus.DUPLICATE
    assert files["inner_link.pdf"].duplicate_of == "real.pdf"
    assert files["real.pdf"].status is FileStatus.DISCOVERED


def test_scan_never_opens_paths_outside_project(make_project):
    """INV-04: scanning project A must not open any file of sibling project B."""
    a = make_project(name="A", contents={"x.pdf": PDF_STUB})
    b = make_project(name="B", contents={"x.pdf": PDF_STUB, "y.xlsx": XLSX_STUB})
    seen_a, stop_a = record_opens(str(a))
    seen_b, stop_b = record_opens(str(b))  # literal and resolved locations (N-3)
    try:
        scan_project(a)
    finally:
        stop_a()
        stop_b()
    assert seen_a, "audit hook recorded nothing; test would be vacuous"
    assert seen_b == []


# ---- F1: resolved-path containment (symlinks, Windows junctions, reparse points)

def test_junction_to_outside_dir_is_rejected_never_traversed_or_opened(make_project, tmp_path):
    outside = tmp_path / "outside_j"
    outside.mkdir()
    (outside / "secret.pdf").write_bytes(PDF_STUB + b"secret")
    root = make_project(contents={"real.pdf": PDF_STUB})
    junction_or_skip(outside, root / "jdir")
    opened, stop = record_opens(str(outside))
    try:
        files = by_path(scan_project(root))
    finally:
        stop()
    assert files["jdir"].status is FileStatus.REJECTED_PATH
    assert "outside the project root" in files["jdir"].reason and files["jdir"].sha256 is None
    assert not any(p.startswith("jdir/") for p in files)
    assert opened == []
    assert files["real.pdf"].status is FileStatus.DISCOVERED


def test_internal_dir_link_is_rejected_not_traversed(make_project):
    root = make_project(contents={"sub/a.pdf": PDF_STUB})
    dir_link_or_skip(root / "sub", root / "alias")
    files = by_path(scan_project(root))
    assert files["alias"].status is FileStatus.REJECTED_PATH
    assert not any(p.startswith("alias/") for p in files)
    assert files["sub/a.pdf"].status is FileStatus.DISCOVERED


def _fake_resolve(mapping):
    real = pathlib.Path.resolve

    def resolve(self, strict=False):
        for name, target in mapping.items():
            if self.name == name:
                return target
        return real(self, strict=strict)
    return resolve


def test_reparse_point_escape_detected_by_resolution_on_any_os(make_project, tmp_path, monkeypatch):
    """Cross-platform: an entry whose resolved path leaves the root is rejected even when
    it is not reported as a symlink (how a Windows junction behaves)."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "x.pdf").write_bytes(PDF_STUB + b"x")
    root = make_project(contents={"weird/inner.pdf": PDF_STUB, "odd.pdf": PDF_STUB + b"o"})
    monkeypatch.setattr(pathlib.Path, "resolve",
                        _fake_resolve({"weird": outside, "odd.pdf": outside / "x.pdf"}))
    opened, stop = record_opens(str(outside))
    try:
        files = by_path(scan_project(root))
    finally:
        stop()
    assert files["weird"].status is FileStatus.REJECTED_PATH
    assert "weird/inner.pdf" not in files
    assert files["odd.pdf"].status is FileStatus.REJECTED_PATH and files["odd.pdf"].sha256 is None
    assert opened == []


# ---- F2: filesystem errors are recorded as UNREADABLE and the scan continues (INV-07)

def _assert_safe_reason(rec, root):
    assert rec.status is FileStatus.UNREADABLE
    assert "Error" in rec.reason  # error class recorded
    assert str(root) not in rec.reason and rec.rel_path.split("/")[-1] not in rec.reason
    assert "Traceback" not in rec.reason


def test_unreadable_file_is_recorded_and_scan_continues(make_project, monkeypatch):
    root = make_project(contents={"a.pdf": PDF_STUB, "b.pdf": PDF_STUB + b"b", "c.pdf": PDF_STUB + b"c"})
    real_open = pathlib.Path.open

    def fake_open(self, *a, **k):
        if self.name == "b.pdf":
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *a, **k)
    monkeypatch.setattr(pathlib.Path, "open", fake_open)
    files = by_path(scan_project(root))
    _assert_safe_reason(files["b.pdf"], root)
    assert "PermissionError" in files["b.pdf"].reason and files["b.pdf"].sha256 is None
    assert files["a.pdf"].status is files["c.pdf"].status is FileStatus.DISCOVERED


def test_unlistable_directory_is_recorded_not_silently_dropped(make_project, monkeypatch):
    root = make_project(contents={"a.pdf": PDF_STUB, "locked/b.pdf": PDF_STUB + b"b"})
    real_scandir = os.scandir

    def fake_scandir(path="."):
        if os.fspath(path).endswith("locked"):
            raise PermissionError(13, "Permission denied", os.fspath(path))
        return real_scandir(path)
    monkeypatch.setattr(os, "scandir", fake_scandir)
    files = by_path(scan_project(root))
    _assert_safe_reason(files["locked"], root)
    assert files["a.pdf"].status is FileStatus.DISCOVERED


def test_unlistable_project_root_is_fatal_not_empty(make_project, monkeypatch):
    root = make_project(contents={"a.pdf": PDF_STUB})
    resolved_root = os.path.normcase(str(root.resolve()))
    real_scandir = os.scandir

    def fake_scandir(path="."):
        if os.path.normcase(os.fspath(path)) == resolved_root:
            raise PermissionError(13, "Permission denied", os.fspath(path))
        return real_scandir(path)
    monkeypatch.setattr(os, "scandir", fake_scandir)
    with pytest.raises(ManifestError, match="cannot be listed"):
        scan_project(root)


def test_file_vanishing_between_listing_and_stat_is_recorded(make_project, monkeypatch):
    root = make_project(contents={"a.pdf": PDF_STUB})
    real_walk = os.walk

    def walk_with_ghost(top, *a, **k):
        for dirpath, dirnames, filenames in real_walk(top, *a, **k):
            if os.path.normcase(dirpath) == os.path.normcase(str(top)):
                filenames = [*filenames, "ghost.pdf"]
            yield dirpath, dirnames, filenames
    monkeypatch.setattr(project_mod.os, "walk", walk_with_ghost)
    files = by_path(scan_project(root))
    _assert_safe_reason(files["ghost.pdf"], root)
    assert "FileNotFoundError" in files["ghost.pdf"].reason
    assert files["a.pdf"].status is FileStatus.DISCOVERED


def test_symlink_loop_is_recorded_and_scan_continues(make_project):
    root = make_project(contents={"a.pdf": PDF_STUB})
    symlink_or_skip(root / "loop2.pdf", root / "loop1.pdf")
    symlink_or_skip(root / "loop1.pdf", root / "loop2.pdf")
    files = by_path(scan_project(root))
    for p in ("loop1.pdf", "loop2.pdf"):
        assert files[p].status in (FileStatus.UNREADABLE, FileStatus.REJECTED_PATH)
        assert files[p].sha256 is None
    assert files["a.pdf"].status is FileStatus.DISCOVERED


@pytest.mark.skipif(sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0,
                    reason="POSIX permission bits; ineffective as root")
def test_posix_chmod_000_file_and_dir(make_project):
    root = make_project(contents={"a.pdf": PDF_STUB, "nope.pdf": PDF_STUB + b"n", "shut/x.pdf": PDF_STUB + b"x"})
    os.chmod(root / "nope.pdf", 0)
    os.chmod(root / "shut", 0)
    try:
        files = by_path(scan_project(root))
    finally:
        os.chmod(root / "nope.pdf", 0o644)
        os.chmod(root / "shut", 0o755)
    assert files["nope.pdf"].status is FileStatus.UNREADABLE
    assert files["shut"].status is FileStatus.UNREADABLE
    assert files["a.pdf"].status is FileStatus.DISCOVERED


# ---- T3: the access recorder is not vacuous for directory listings

def test_access_recorder_sees_directory_listings(make_project):
    root = make_project(contents={"sub/a.pdf": PDF_STUB})
    seen, stop = record_opens(str(root))
    try:
        scan_project(root)
    finally:
        stop()
    events = {e for e, _ in seen}
    assert "os.scandir" in events and "open" in events


# ---- T1: directory resolve failures and RuntimeError (symlink loop) are UNREADABLE

def _raising_resolve(names, exc_factory):
    real = pathlib.Path.resolve

    def resolve(self, strict=False):
        if self.name in names:
            raise exc_factory()
        return real(self, strict=strict)
    return resolve


def test_directory_resolve_permission_error_is_unreadable_and_not_traversed(make_project, monkeypatch):
    root = make_project(contents={"guarded/inner.pdf": PDF_STUB, "a.pdf": PDF_STUB + b"a"})
    monkeypatch.setattr(pathlib.Path, "resolve",
                        _raising_resolve({"guarded"}, lambda: PermissionError(13, "Permission denied")))
    files = by_path(scan_project(root))
    _assert_safe_reason(files["guarded"], root)
    assert "could not be resolved" in files["guarded"].reason
    assert "guarded/inner.pdf" not in files  # M9: never traversed
    assert files["a.pdf"].status is FileStatus.DISCOVERED


@pytest.mark.parametrize("name,rel", [("loopdir", "loopdir"), ("loop.pdf", "loop.pdf")])
def test_runtime_error_from_resolve_is_unreadable(make_project, monkeypatch, name, rel):
    """Python 3.11/3.12 raise RuntimeError for symlink loops (M8)."""
    root = make_project(contents={"loopdir/x.pdf": PDF_STUB, "loop.pdf": PDF_STUB + b"l", "a.pdf": PDF_STUB + b"a"})
    monkeypatch.setattr(pathlib.Path, "resolve",
                        _raising_resolve({name}, lambda: RuntimeError("Symlink loop")))
    files = by_path(scan_project(root))
    _assert_safe_reason(files[rel], root)
    assert "RuntimeError" in files[rel].reason
    assert files["a.pdf"].status is FileStatus.DISCOVERED


def test_windows_acl_denied_file_and_directory_are_unreadable(make_project):
    from conftest import windows_access_denied
    root = make_project(contents={"a.pdf": PDF_STUB, "nope.pdf": PDF_STUB + b"n", "shut/x.pdf": PDF_STUB + b"x"})
    with windows_access_denied(root / "nope.pdf"), windows_access_denied(root / "shut"):
        files = by_path(scan_project(root))
    for p in ("nope.pdf", "shut"):
        _assert_safe_reason(files[p], root)
        assert "PermissionError" in files[p].reason
    assert "shut/x.pdf" not in files
    assert files["a.pdf"].status is FileStatus.DISCOVERED


# ---- L-5: a directory vanishing between listing and check is UNREADABLE, not a link

def test_directory_vanishing_after_listing_is_unreadable(make_project, monkeypatch):
    root = make_project(contents={"a.pdf": PDF_STUB})
    real_walk = os.walk

    def walk_with_ghost_dir(top, *a, **k):
        for dirpath, dirnames, filenames in real_walk(top, *a, **k):
            if os.path.normcase(dirpath) == os.path.normcase(str(top)):
                dirnames.append("ghostdir")
            yield dirpath, dirnames, filenames
    monkeypatch.setattr(project_mod.os, "walk", walk_with_ghost_dir)
    files = by_path(scan_project(root))
    _assert_safe_reason(files["ghostdir"], root)
    assert "FileNotFoundError" in files["ghostdir"].reason


def test_dangling_junction_is_rejected_not_unreadable(make_project, tmp_path):
    target = tmp_path / "gone"
    target.mkdir()
    root = make_project(contents={"a.pdf": PDF_STUB})
    junction_or_skip(target, root / "dangling")
    target.rmdir()
    files = by_path(scan_project(root))
    assert files["dangling"].status is FileStatus.REJECTED_PATH
    assert "does not resolve" in files["dangling"].reason


# ---- N-3: the access recorder sees access through a junction/symlink to an outside target

def test_access_recorder_detects_access_through_link_to_outside(make_project, tmp_path):
    outside = tmp_path / "outside_rec"
    outside.mkdir()
    (outside / "secret.pdf").write_bytes(PDF_STUB)
    root = make_project()
    dir_link_or_skip(outside, root / "jdir")
    seen, stop = record_opens(str(outside))
    try:
        (root / "jdir" / "secret.pdf").read_bytes()  # literal path is inside the project
        os.listdir(root / "jdir")
    finally:
        stop()
    events = {e for e, _ in seen}
    assert "open" in events and "os.listdir" in events


# ---- N-1: manifest entries match files by exact path, then by file identity (no case folding)

def _issues(scan, text):
    return [i for i in scan.manifest.issues if text in i.problem]


def _same_file_issues(scan, effect_text):
    return [i for i in scan.manifest.issues if "name the same path" in i.problem and effect_text in i.effect]


@pytest.fixture
def ci_project(make_project, tmp_path):
    """make_project on a filesystem that itself resolves names case-insensitively."""
    from conftest import fs_is_case_insensitive
    if not fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive filesystem (e.g. default NTFS)")
    return make_project


def test_n1_case_variant_entry_is_matched_by_identity_not_downgraded(ci_project):
    """M-1 scenario 1: default synthetic, entry 'Secret.pdf: confidential', disk 'secret.pdf'."""
    root = ci_project(contents={"secret.pdf": PDF_STUB}, default_classification="synthetic",
                      files=[{"path": "Secret.pdf", "classification": "confidential"}])
    scan = scan_project(root)
    r = by_path(scan)["secret.pdf"]
    assert r.classification is Classification.CONFIDENTIAL
    assert r.classification_source is ClassificationSource.MANIFEST_FILE_ENTRY
    assert not _issues(scan, "not found")
    assert _issues(scan, "under another spelling")


@pytest.mark.parametrize("order", [0, 1])
def test_n1_case_variant_entries_for_one_file_take_most_restrictive(ci_project, order):
    """M-1 scenario 2: 'Docs/A.pdf: confidential' and 'docs/a.pdf: synthetic', one file."""
    decls = [{"path": "Docs/A.pdf", "classification": "confidential"},
             {"path": "docs/a.pdf", "classification": "synthetic"}]
    if order:
        decls.reverse()
    root = ci_project(contents={"docs/a.pdf": PDF_STUB}, default_classification="synthetic", files=decls)
    scan = scan_project(root)
    assert by_path(scan)["docs/a.pdf"].classification is Classification.CONFIDENTIAL
    assert _same_file_issues(scan, "most restrictive classification applies: confidential")


def test_n1_simulated_case_sensitive_distinct_files_are_not_merged(make_project, monkeypatch):
    """Required test 1, any OS: two distinct files 'A.pdf' and 'a.pdf' (distinct file IDs) and
    a case-sensitive lookup. A declaration for one must never reach the other."""
    from wall_e.project import _apply_declarations, _record, load_manifest
    root = make_project(files=[{"path": "a.pdf", "classification": "synthetic"},
                               {"path": "B.pdf", "classification": "synthetic"}])
    manifest, _ = load_manifest(root)
    records = [_record(p, FileType.PDF, FileStatus.DISCOVERED, manifest) for p in ("A.pdf", "a.pdf", "b.pdf")]
    ids = {"A.pdf": (1, 10), "a.pdf": (1, 11), "b.pdf": (1, 12)}

    def case_sensitive_lookup(root, rel, dir_ids):
        raise FileNotFoundError(rel)  # 'B.pdf' does not exist in a case-sensitive directory
    monkeypatch.setattr(project_mod, "_resolve_declared", case_sensitive_lookup)
    out, issues = _apply_declarations(root, records, ids, {"": (1, 1)}, manifest)
    cls = {r.rel_path: r.classification for r in out}
    assert cls == {"A.pdf": Classification.CONFIDENTIAL, "a.pdf": Classification.SYNTHETIC,
                   "b.pdf": Classification.CONFIDENTIAL}
    assert [i.field for i in issues] == ["files:B.pdf"] and "not found" in issues[0].problem


@pytest.mark.skipif(os.name != "nt", reason="real NTFS upcase table")
@pytest.mark.parametrize("declared,on_disk", [("kalıp.pdf", "KALIP.pdf"), ("straße.pdf", "STRASSE.pdf")])
@pytest.mark.parametrize("both_exist", [False, True])
def test_n1_ntfs_distinct_names_are_not_merged(make_project, declared, on_disk, both_exist):
    """Required test 2: NTFS keeps 'kalıp.pdf' (dotless i) and 'KALIP.pdf' distinct; the old
    case key merged them and let the unlisted KALIP.pdf inherit 'synthetic'."""
    contents = {on_disk: PDF_STUB + b"upper"}
    if both_exist:
        contents[declared] = PDF_STUB + b"lower"
    root = make_project(contents=contents, files=[{"path": declared, "classification": "synthetic"}])
    scan = scan_project(root)
    files = by_path(scan)
    assert set(files) == set(contents)  # precondition: NTFS really keeps both names
    assert files[on_disk].classification is Classification.CONFIDENTIAL
    assert files[on_disk].classification_source is ClassificationSource.BUILT_IN_DEFAULT
    if both_exist:
        assert files[declared].classification is Classification.SYNTHETIC
    else:
        assert any(i.field == f"files:{declared}" and "not found" in i.problem for i in scan.manifest.issues)


def test_n1_case_sensitive_directory_keeps_case_variants_distinct(make_project):
    """Required test 3: NTFS per-directory case sensitivity (fsutil) or a case-sensitive FS."""
    from conftest import case_sensitive_dir_or_skip
    root = make_project(files=[{"path": "cs/a.pdf", "classification": "synthetic"},
                               {"path": "cs/B.pdf", "classification": "synthetic"}])
    cs = case_sensitive_dir_or_skip(root / "cs")
    for name in ("A.pdf", "a.pdf", "b.pdf"):
        (cs / name).write_bytes(PDF_STUB + name.encode())
    scan = scan_project(root)
    files = by_path(scan)
    assert {p for p in files if p.startswith("cs/")} == {"cs/A.pdf", "cs/a.pdf", "cs/b.pdf"}
    assert files["cs/a.pdf"].classification is Classification.SYNTHETIC
    assert files["cs/A.pdf"].classification is Classification.CONFIDENTIAL
    assert files["cs/b.pdf"].classification is Classification.CONFIDENTIAL
    assert any(i.field == "files:cs/B.pdf" and "not found" in i.problem for i in scan.manifest.issues)


@pytest.mark.skipif(os.name != "nt", reason="real NTFS upcase table")
def test_n1_ntfs_greek_case_pair_is_one_file(make_project):
    """Required test 4: NTFS maps U+1F80 to U+1F88 (one file); the old key kept them apart
    (str.upper gives two characters), so the confidential entry was lost."""
    root = make_project(contents={"ᾈ.pdf": PDF_STUB}, default_classification="synthetic",
                        files=[{"path": "ᾀ.pdf", "classification": "confidential"}])
    if not (root / "ᾀ.pdf").exists():
        pytest.skip("this volume's upcase table does not map U+1F80 to U+1F88")
    scan = scan_project(root)
    r = by_path(scan)["ᾈ.pdf"]
    assert r.classification is Classification.CONFIDENTIAL
    assert not _issues(scan, "not found")


def test_f3_hard_link_classifications_are_path_specific(make_project):
    """F-3: names of one file (hard links) keep their own classification; an undeclared name
    keeps default_classification even though another name of the file is declared lower."""
    from conftest import hardlink_or_skip
    root = make_project(contents={"a.pdf": PDF_STUB, "d2/x.txt": b"x"},
                        files=[{"path": "a.pdf", "classification": "synthetic"},
                               {"path": "b.pdf", "classification": "public-licensed"}])
    hardlink_or_skip(root / "a.pdf", root / "b.pdf")
    hardlink_or_skip(root / "a.pdf", root / "c.pdf")     # undeclared, same directory
    hardlink_or_skip(root / "a.pdf", root / "d2" / "z.pdf")  # undeclared, other directory
    scan = scan_project(root)
    files = by_path(scan)
    assert files["a.pdf"].classification is Classification.SYNTHETIC
    assert files["b.pdf"].classification is Classification.PUBLIC_LICENSED
    for p in ("c.pdf", "d2/z.pdf"):
        assert files[p].classification is Classification.CONFIDENTIAL, p
        assert files[p].classification_source is ClassificationSource.BUILT_IN_DEFAULT, p
    [alias] = [i for i in scan.manifest.issues if "hard links" in i.problem]
    assert "a.pdf" in alias.problem and "d2/z.pdf" in alias.problem and "not transferred" in alias.effect
    assert not _issues(scan, "name the same path") and not _issues(scan, "under another spelling")


@pytest.mark.skipif(os.name != "nt", reason="exact on-disk name via the Windows final-path query")
def test_f3_case_variant_entry_applies_only_to_the_named_hard_link(ci_project):
    from conftest import hardlink_or_skip
    root = ci_project(contents={"a.pdf": PDF_STUB}, default_classification="synthetic",
                      files=[{"path": "A.PDF", "classification": "confidential"}])
    hardlink_or_skip(root / "a.pdf", root / "b.pdf")
    scan = scan_project(root)
    files = by_path(scan)
    assert files["a.pdf"].classification is Classification.CONFIDENTIAL
    assert files["b.pdf"].classification is Classification.SYNTHETIC
    assert [i.effect for i in scan.manifest.issues if i.field == "files:A.PDF"] == ["classification applied to 'a.pdf'"]


def test_f3_ambiguous_hard_link_spelling_is_not_applied_and_reported(make_project, monkeypatch):
    """Any OS: a spelling naming one of several same-directory hard links, where the filesystem
    does not say which, is applied to none of them (never transferred), with an issue."""
    from wall_e.project import _apply_declarations, _record, load_manifest
    root = make_project(default_classification="synthetic",
                        files=[{"path": "A.PDF", "classification": "confidential"}])
    manifest, _ = load_manifest(root)
    records = [_record(p, FileType.PDF, FileStatus.DISCOVERED, manifest) for p in ("a.pdf", "b.pdf")]
    monkeypatch.setattr(project_mod, "_resolve_declared", lambda root, rel, dir_ids: ((1, 1), (1, 10), 2))
    monkeypatch.setattr(project_mod, "_on_disk_rel", lambda root, rel: None)
    out, issues = _apply_declarations(root, records, {"a.pdf": (1, 10), "b.pdf": (1, 10)}, {"": (1, 1)}, manifest)
    assert {r.rel_path: r.classification for r in out} == {"a.pdf": Classification.SYNTHETIC,
                                                         "b.pdf": Classification.SYNTHETIC}
    [issue] = [i for i in issues if i.field == "files:A.PDF"]
    assert "could not be confirmed" in issue.problem and issue.effect == "entry ignored"


# ---- F-A: a non-exact spelling is applied only once confirmed to name that very path

def _single_candidate(make_project, monkeypatch, on_disk, nlink):
    """One discovered path 'a.pdf'; the entry 'A.PDF' resolves to the same file (simulated)."""
    from wall_e.project import _apply_declarations, _record, load_manifest
    root = make_project(files=[{"path": "A.PDF", "classification": "synthetic"}])  # default: confidential
    manifest, _ = load_manifest(root)
    records = [_record("a.pdf", FileType.PDF, FileStatus.DISCOVERED, manifest)]
    monkeypatch.setattr(project_mod, "_resolve_declared", lambda root, rel, dir_ids: ((1, 1), (1, 10), nlink))
    monkeypatch.setattr(project_mod, "_on_disk_rel", lambda root, rel: on_disk)
    out, issues = _apply_declarations(root, records, {"a.pdf": (1, 10)}, {"": (1, 1)}, manifest)
    return out[0], [i for i in issues if i.field == "files:A.PDF"]


@pytest.mark.parametrize("on_disk,nlink", [("other.pdf", 1), ("other.pdf", 2), (None, 2)])
def test_fa_unconfirmed_single_candidate_is_not_applied(make_project, monkeypatch, on_disk, nlink):
    """Any OS: the spelling names another name of the file (on-disk name differs), or no on-disk
    name is available and the file has several names -> never applied to 'a.pdf'."""
    r, [issue] = _single_candidate(make_project, monkeypatch, on_disk, nlink)
    assert r.classification is Classification.CONFIDENTIAL
    assert r.classification_source is ClassificationSource.BUILT_IN_DEFAULT
    assert "could not be confirmed" in issue.problem and issue.effect == "entry ignored"


@pytest.mark.parametrize("on_disk,nlink", [("a.pdf", 1), ("a.pdf", 3), (None, 1)])
def test_fa_confirmed_single_candidate_is_applied(make_project, monkeypatch, on_disk, nlink):
    """Positive control: confirmed by on-disk name, or the file's only name (link count 1)."""
    r, [issue] = _single_candidate(make_project, monkeypatch, on_disk, nlink)
    assert r.classification is Classification.SYNTHETIC
    assert issue.effect == "classification applied to 'a.pdf'"


def test_fa_entry_for_the_manifest_never_reaches_a_hard_link_of_it(make_project):
    """Reviewer probe P3, any OS: 'project.json' is hard-linked to 'a.pdf'; an entry for the
    manifest's own path must not lower the undeclared 'a.pdf'."""
    from conftest import hardlink_or_skip
    root = make_project(files=[{"path": "project.json", "classification": "synthetic"}])
    hardlink_or_skip(root / "project.json", root / "a.pdf")
    scan = scan_project(root)
    r = by_path(scan)["a.pdf"]
    assert r.classification is Classification.CONFIDENTIAL
    assert r.classification_source is ClassificationSource.BUILT_IN_DEFAULT
    [issue] = [i for i in scan.manifest.issues if i.field == "files:project.json"]
    assert "not found" in issue.problem and issue.effect == "entry ignored"
    assert not _issues(scan, "under another spelling")
    if os.name == "nt":
        assert "project manifest" in issue.problem


def test_fa_case_variant_of_the_manifest_never_reaches_a_hard_link_of_it(ci_project):
    """Reviewer probe P3 exactly: 'PROJECT.JSON: synthetic' on a case-insensitive filesystem."""
    from conftest import hardlink_or_skip
    root = ci_project(files=[{"path": "PROJECT.JSON", "classification": "synthetic"}])
    hardlink_or_skip(root / "project.json", root / "a.pdf")
    scan = scan_project(root)
    r = by_path(scan)["a.pdf"]
    assert r.classification is Classification.CONFIDENTIAL
    assert r.classification_source is ClassificationSource.BUILT_IN_DEFAULT
    [issue] = [i for i in scan.manifest.issues if i.field == "files:PROJECT.JSON"]
    assert "not found" in issue.problem and issue.effect == "entry ignored"
    assert not _issues(scan, "under another spelling")


# ---- Classification-source tie-break (deterministic; documented in _apply_declarations)

def _tie_break(make_project, monkeypatch, decls):
    from wall_e.project import _apply_declarations, _record, load_manifest
    root = make_project(default_classification="synthetic", files=decls)
    manifest, _ = load_manifest(root)
    records = [_record("docs/a.pdf", FileType.PDF, FileStatus.DISCOVERED, manifest)]
    # every other spelling names docs/a.pdf, as on a case-insensitive filesystem
    monkeypatch.setattr(project_mod, "_resolve_declared", lambda root, rel, dir_ids: ((1, 2), (1, 10), 1))
    monkeypatch.setattr(project_mod, "_on_disk_rel", lambda root, rel: "docs/a.pdf")
    out, _ = _apply_declarations(root, records, {"docs/a.pdf": (1, 10)}, {"": (1, 1), "docs": (1, 2)}, manifest)
    return out[0]


@pytest.mark.parametrize("order", [0, 1])
def test_tie_break_exact_path_entry_supplies_classification_source(make_project, monkeypatch, order):
    decls = [{"path": "docs/a.pdf"},                                   # no key: default, manifest_default
             {"path": "Docs/A.pdf", "classification": "synthetic"}]    # explicit: manifest_file_entry
    r = _tie_break(make_project, monkeypatch, decls[::-1] if order else decls)
    assert r.classification is Classification.SYNTHETIC
    assert r.classification_source is ClassificationSource.MANIFEST_DEFAULT  # the exact-path entry


@pytest.mark.parametrize("order", [0, 1])
def test_tie_break_without_exact_entry_takes_first_in_path_order(make_project, monkeypatch, order):
    decls = [{"path": "Docs/A.pdf", "classification": "synthetic"},    # manifest_file_entry
             {"path": "DOCS/A.PDF"}]                                   # manifest_default; sorts first
    r = _tie_break(make_project, monkeypatch, decls[::-1] if order else decls)
    assert r.classification is Classification.SYNTHETIC
    assert r.classification_source is ClassificationSource.MANIFEST_DEFAULT  # 'DOCS/A.PDF' < 'Docs/A.pdf'


def _lstat_without_file_ids(monkeypatch):
    real = os.lstat

    def lstat(p, *a, **k):
        st = real(p, *a, **k)
        return os.stat_result((st.st_mode, 0, st.st_dev, st.st_nlink, st.st_uid, st.st_gid, st.st_size,
                               int(st.st_atime), int(st.st_mtime), int(st.st_ctime)))
    monkeypatch.setattr(project_mod.os, "lstat", lstat)


def test_n1_without_file_identity_only_exact_paths_match(make_project, monkeypatch):
    """Documented fallback (st_ino == 0): exact path matching only; an entry that names the
    file under another spelling is not applied and is reported, never silently."""
    from conftest import fs_is_case_insensitive
    root = make_project(contents={"a.pdf": PDF_STUB, "b.pdf": PDF_STUB + b"b"}, default_classification="synthetic",
                        files=[{"path": "b.pdf", "classification": "confidential"},
                               {"path": "A.PDF", "classification": "confidential"}])
    _lstat_without_file_ids(monkeypatch)
    scan = scan_project(root)
    monkeypatch.undo()
    files = by_path(scan)
    assert files["b.pdf"].classification is Classification.CONFIDENTIAL  # exact path
    assert files["a.pdf"].classification is Classification.SYNTHETIC     # identity unavailable
    [issue] = [i for i in scan.manifest.issues if i.field == "files:A.PDF"]
    assert "not found" in issue.problem and issue.effect == "entry ignored"
    if fs_is_case_insensitive(root):
        assert "reports no file identity" in issue.problem


_XP = "\\\\?\\"


def _plain(p: str) -> str:
    """Strip a Windows extended-length prefix (\\\\?\\ or \\\\?\\UNC\\) so paths compare."""
    if p.startswith(_XP + "UNC\\"):
        return "\\\\" + p[len(_XP) + 4:]
    return p[len(_XP):] if p.startswith(_XP) else p


def _record_lstat(monkeypatch):
    calls = []
    real = os.lstat

    def lstat(p, *a, **k):
        calls.append(os.path.normcase(os.path.abspath(_plain(os.fsdecode(p)))))
        return real(p, *a, **k)
    monkeypatch.setattr(project_mod.os, "lstat", lstat)
    return calls


def test_n1_identity_lookup_never_passes_through_links(make_project, tmp_path, monkeypatch):
    outside = tmp_path / "outside_n1"
    outside.mkdir()
    (outside / "secret.pdf").write_bytes(PDF_STUB + b"s")
    root = make_project(contents={"a.pdf": PDF_STUB},
                        files=[{"path": "jdir/secret.pdf", "classification": "synthetic"},
                               {"path": "jdir/Secret.pdf", "classification": "synthetic"}])
    dir_link_or_skip(outside, root / "jdir")
    calls = _record_lstat(monkeypatch)
    opened, stop = record_opens(str(outside))
    try:
        scan = scan_project(root)
    finally:
        stop()
        monkeypatch.undo()
    through = os.path.normcase(str(root.resolve() / "jdir")) + os.sep
    secret = os.path.normcase(str((outside / "secret.pdf").resolve()))
    assert calls and not [c for c in calls if c.startswith(through) or c == secret]
    assert opened == []
    for p in ("jdir/secret.pdf", "jdir/Secret.pdf"):
        [issue] = [i for i in scan.manifest.issues if i.field == f"files:{p}"]
        assert "did not traverse" in issue.problem


def test_n1_windows_device_names_colons_and_nul_are_never_looked_up(make_project, monkeypatch):
    """Includes F-2: 'NUL ' (trailing space) still maps to the NUL device through Win32 on
    this Windows 11 build; it must never be looked up (no lstat, no open)."""
    monkeypatch.setattr(project_mod, "WINDOWS_PATH_RULES", True)
    names = ("NUL", "NUL ", "CON .pdf", "con.pdf", "sub/COM1.txt", "a.pdf:stream", "sub/c:x.pdf", "LPT¹")
    root = make_project(contents={"a.pdf": PDF_STUB, "sub/x.pdf": PDF_STUB + b"x"},
                        files=[*({"path": n, "classification": "synthetic"} for n in names),
                               {"path": "a\u0000.pdf", "classification": "synthetic"}])
    calls = _record_lstat(monkeypatch)
    opened, stop = record_opens(str(root))
    try:
        scan = scan_project(root)
    finally:
        stop()
        monkeypatch.undo()
    special = {os.path.normcase(n.rsplit("/", 1)[-1]) for n in names}
    assert not {os.path.basename(p) for _, p in opened} & special  # no content read via these names
    looked_up = {c.rsplit(os.sep, 1)[-1] for c in calls}
    assert not looked_up & {os.path.normcase(n.rsplit("/", 1)[-1]) for n in names}
    assert by_path(scan)["a.pdf"].classification is Classification.CONFIDENTIAL  # not via 'a.pdf:stream'
    for n in names:
        [issue] = [i for i in scan.manifest.issues if i.field == f"files:{n}"]
        assert "device name" in issue.problem
    [nul] = [i for i in scan.manifest.issues if i.field == "files:a\u0000.pdf"]
    assert "not found" in nul.problem and "ValueError" in nul.problem


# ---- F-1: identity lookups use extended-length paths on Windows (no trailing-dot/space stripping)

@pytest.mark.skipif(os.name != "nt", reason="Win32 trailing dot/space normalisation")
@pytest.mark.parametrize("special", ["a.pdf.", "a.pdf "])
def test_f1_trailing_dot_or_space_name_keeps_its_own_label(make_project, monkeypatch, special):
    """A distinct file 'a.pdf.' / 'a.pdf ' must not get the identity, or the label, of 'a.pdf'."""
    from conftest import windows_special_names
    root = make_project(contents={"a.pdf": PDF_STUB}, files=[{"path": "a.pdf", "classification": "synthetic"}])
    root_nc = os.path.normcase(str(root.resolve()))
    with windows_special_names(root, {special: PDF_STUB + b"a different file"}):
        calls = _record_lstat(monkeypatch)
        try:
            scan = scan_project(root)
        finally:
            monkeypatch.undo()
    files = by_path(scan)
    assert set(files) == {"a.pdf", special}  # reported under its own discovered name
    assert files["a.pdf"].classification is Classification.SYNTHETIC
    assert files[special].classification is Classification.CONFIDENTIAL
    assert files[special].classification_source is ClassificationSource.BUILT_IN_DEFAULT
    assert not [i for i in scan.manifest.issues if repr(special) in i.problem or repr(special) in i.effect]
    # project-root isolation: every metadata lookup stayed inside the project
    assert calls and all(_under(c, root_nc) for c in calls), [c for c in calls if not _under(c, root_nc)]


@pytest.mark.skipif(os.name != "nt", reason="Win32 trailing dot/space normalisation")
def test_f1_trailing_dot_or_space_entries_name_only_themselves(make_project):
    """Entries 'a.pdf.', 'a.pdf ', 'A.PDF.' do not silently apply to the different file 'a.pdf'."""
    root = make_project(contents={"a.pdf": PDF_STUB},
                        files=[{"path": p, "classification": "synthetic"} for p in ("a.pdf.", "a.pdf ", "A.PDF.")])
    scan = scan_project(root)
    assert by_path(scan)["a.pdf"].classification is Classification.CONFIDENTIAL
    for p in ("a.pdf.", "a.pdf ", "A.PDF."):
        [issue] = [i for i in scan.manifest.issues if i.field == f"files:{p}"]
        assert "not found" in issue.problem and issue.effect == "entry ignored"


@pytest.mark.skipif(os.name != "nt", reason="NTFS case rules through extended-length paths")
def test_f1_ntfs_case_still_resolves_for_trailing_dot_names(make_project):
    """'A.PDF.' names the distinct file 'a.pdf.' (NTFS case-insensitivity is kept), never 'a.pdf'."""
    from conftest import windows_special_names
    root = make_project(contents={"a.pdf": PDF_STUB}, default_classification="synthetic",
                        files=[{"path": "A.PDF.", "classification": "confidential"}])
    with windows_special_names(root, {"a.pdf.": PDF_STUB + b"dot"}):
        scan = scan_project(root)
    files = by_path(scan)
    assert files["a.pdf."].classification is Classification.CONFIDENTIAL
    assert files["a.pdf"].classification is Classification.SYNTHETIC


@pytest.mark.skipif(os.name != "nt", reason="NTFS 8.3 short names")
def test_f1_short_8dot3_names_still_resolve(make_project):
    root = make_project(contents={"sub/SomeLongName.pdf": PDF_STUB}, default_classification="synthetic",
                        files=[{"path": "SUB/SOMELO~1.PDF", "classification": "confidential"}])
    if not os.path.exists(root / "sub" / "SOMELO~1.PDF"):
        pytest.skip("8.3 short names are disabled on this volume")
    scan = scan_project(root)
    assert by_path(scan)["sub/SomeLongName.pdf"].classification is Classification.CONFIDENTIAL
    assert [i.effect for i in scan.manifest.issues if i.field == "files:SUB/SOMELO~1.PDF"] == [
        "classification applied to 'sub/SomeLongName.pdf'"]


