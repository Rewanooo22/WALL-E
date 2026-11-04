"""File discovery, hashing, classification, duplicates, path safety, isolation
(spec §4.1, §7.7, §12 step 1, §14.1, INV-04, INV-07)."""

import hashlib
import os
import sys

import pytest

from conftest import PDF_STUB, XLSX_STUB
from wall_e.models import Classification, ClassificationSource, FileStatus, FileType
from wall_e.project import Limits, scan_project


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


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks")
def test_symlinks_escaping_root_are_rejected_and_dirs_not_traversed(make_project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.pdf").write_bytes(PDF_STUB)
    root = make_project(contents={"real.pdf": PDF_STUB + b"r"})
    os.symlink(outside / "secret.pdf", root / "link.pdf")
    os.symlink(outside, root / "linkdir")
    os.symlink(root / "real.pdf", root / "inner_link.pdf")
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
    b_root = str(b.resolve())
    opened = []
    active = True

    def hook(event, args):
        if active and event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            opened.append(os.fsdecode(args[0]))

    sys.addaudithook(hook)
    try:
        scan_project(a)
    finally:
        active = False
    assert opened, "audit hook recorded nothing; test would be vacuous"
    assert not [p for p in opened if os.path.abspath(p).startswith(b_root)]
