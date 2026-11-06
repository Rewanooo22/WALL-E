"""Run directory and run manifest (spec §12 step 7, INV-08)."""

import json

import pytest

from conftest import PDF_STUB
from wall_e.project import Limits, scan_project
from wall_e.run import (
    OutputDirError, build_run_manifest, create_run_dir, stable_view, write_run_manifest,
)


def test_run_manifest_contents_and_determinism(make_project, tmp_path):
    root = make_project(contents={"s.pdf": PDF_STUB, "n.txt": b"x"})
    out = tmp_path / "out"
    m1 = build_run_manifest(scan_project(root), Limits(), "r1")
    m2 = build_run_manifest(scan_project(root), Limits(), "r2")
    assert stable_view(m1) == stable_view(m2)
    assert {d for d in m1["dependencies"]} >= {"pdfplumber", "pdfminer.six", "pypdfium2", "openpyxl", "pydantic"}
    assert [i["path"] for i in m1["inputs"]] == ["n.txt", "s.pdf"]
    assert m1["manifest_sha256"] and m1["config_sha256"]

    run_id, run_dir = create_run_dir(out, scan_project(root), run_id="r1")
    assert run_dir == (out / "TEST-1" / "r1").resolve()
    p = write_run_manifest(run_dir, m1)
    assert json.loads(p.read_text())["run_id"] == "r1"
    with pytest.raises(OutputDirError):
        write_run_manifest(run_dir, m1)


def test_config_change_changes_hash(make_project):
    scan = scan_project(make_project())
    assert (build_run_manifest(scan, Limits(), "r")["config_sha256"]
            != build_run_manifest(scan, Limits(max_file_bytes=1), "r")["config_sha256"])


def test_run_dirs_are_immutable_and_outside_project(make_project, tmp_path):
    root = make_project()
    scan = scan_project(root)
    create_run_dir(tmp_path / "out", scan, run_id="same")
    with pytest.raises(OutputDirError, match="exists"):
        create_run_dir(tmp_path / "out", scan, run_id="same")
    with pytest.raises(OutputDirError, match="inside the project"):
        create_run_dir(root / "out", scan)


# ---- F3: output directory safety

def test_run_dir_inside_project_via_parent_out_root_is_rejected(tmp_path):
    """Probe P7: project at <out>/TEST-1 and out_root=<out> would put the run inside the project."""
    from conftest import write_manifest
    root = tmp_path / "out" / "TEST-1"
    write_manifest(root)
    (root / "s.pdf").write_bytes(PDF_STUB)
    scan = scan_project(root)
    with pytest.raises(OutputDirError, match="inside the project"):
        create_run_dir(tmp_path / "out", scan, run_id="r1")
    assert [f.rel_path for f in scan_project(root).files] == ["s.pdf"]  # nothing written


def test_run_dir_that_is_an_ancestor_of_the_project_is_rejected(tmp_path):
    from conftest import write_manifest
    root = tmp_path / "out" / "TEST-1" / "r1" / "proj"
    write_manifest(root)
    with pytest.raises(OutputDirError, match="ancestor"):
        create_run_dir(tmp_path / "out", scan_project(root), run_id="r1")


@pytest.mark.parametrize("bad", ["../../escaped", "..", "a/b", "a\\b", "a\b", "", " ", "a b", "x" * 65,
                                 "r1\n", "é", 5])
def test_invalid_run_ids_are_rejected(make_project, tmp_path, bad):
    """Probe P8: run_id='../../x' escaped out_root."""
    scan = scan_project(make_project())
    with pytest.raises(OutputDirError, match="run_id"):
        create_run_dir(tmp_path / "out", scan, run_id=bad)
    assert not (tmp_path / "escaped").exists()


def test_run_dir_escaping_out_root_via_linked_project_dir_is_rejected(make_project, tmp_path):
    from conftest import dir_link_or_skip
    scan = scan_project(make_project())
    out = tmp_path / "out"
    out.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    dir_link_or_skip(elsewhere, out / "TEST-1")
    with pytest.raises(OutputDirError, match="escapes"):
        create_run_dir(out, scan, run_id="r1")
    assert list(elsewhere.iterdir()) == []


def test_default_run_id_is_valid(make_project, tmp_path):
    run_id, run_dir = create_run_dir(tmp_path / "out", scan_project(make_project()))
    assert len(run_id) == 32 and run_dir.name == run_id and run_dir.is_dir()


def test_omitted_run_id_is_generated_but_explicit_empty_is_invalid(make_project, tmp_path):
    """Rule D: None -> generated; "" -> rejected (never silently replaced)."""
    scan = scan_project(make_project())
    run_id, _ = create_run_dir(tmp_path / "out", scan, run_id=None)
    assert run_id
    with pytest.raises(OutputDirError, match="run_id"):
        create_run_dir(tmp_path / "out", scan, run_id="")


# ---- L-2: a link under out_root must not redirect a run into another project's outputs

def test_run_dir_redirected_into_other_project_outputs_is_rejected(make_project, tmp_path):
    from conftest import dir_link_or_skip
    scan = scan_project(make_project())
    out = tmp_path / "out"
    other = out / "OTHER-9"
    other.mkdir(parents=True)
    dir_link_or_skip(other, out / "TEST-1")
    with pytest.raises(OutputDirError, match="link or reparse point"):
        create_run_dir(out, scan, run_id="r1")
    assert list(other.iterdir()) == []


def test_run_dir_redirect_detected_by_resolution_on_any_os(make_project, tmp_path, monkeypatch):
    """Cross-platform: resolution that differs from the literal path is refused."""
    import pathlib
    scan = scan_project(make_project())
    out = (tmp_path / "out").resolve()
    real = pathlib.Path.resolve

    def fake(self, strict=False):
        if self.name == "r1" and self.parent.name == "TEST-1":
            return out / "OTHER-9" / "r1"
        return real(self, strict=strict)
    monkeypatch.setattr(pathlib.Path, "resolve", fake)
    with pytest.raises(OutputDirError, match="link or reparse point"):
        create_run_dir(out, scan, run_id="r1")


# ---- L-3: Windows reserved device names and failed creation

@pytest.fixture
def reserved_names_apply(monkeypatch):
    import wall_e.run as run_mod
    monkeypatch.setattr(run_mod, "WINDOWS_RESERVED_NAMES_APPLY", True)


@pytest.mark.parametrize("name", ["NUL", "con", "Aux", "PRN", "COM1", "com9", "LPT0", "lpt9"])
def test_reserved_run_id_is_rejected(make_project, tmp_path, reserved_names_apply, name):
    with pytest.raises(OutputDirError, match="reserved device name"):
        create_run_dir(tmp_path / "out", scan_project(make_project()), run_id=name)


def test_reserved_project_id_is_rejected_for_outputs(make_project, tmp_path, reserved_names_apply):
    scan = scan_project(make_project(project_id="NUL"))
    with pytest.raises(OutputDirError, match="project_id 'NUL' is a reserved device name"):
        create_run_dir(tmp_path / "out", scan, run_id="r1")


def test_reserved_names_check_is_on_for_windows_only():
    import sys

    import wall_e.run as run_mod
    assert run_mod.WINDOWS_RESERVED_NAMES_APPLY is (sys.platform == "win32")


def test_non_reserved_lookalikes_are_accepted(make_project, tmp_path, reserved_names_apply):
    scan = scan_project(make_project())
    for name in ("NULL", "CONSOLE", "COM10", "LPT", "AUX1x"):
        create_run_dir(tmp_path / "out", scan, run_id=name)


def test_mkdir_os_error_becomes_output_dir_error(make_project, tmp_path, monkeypatch):
    import pathlib
    scan = scan_project(make_project())

    def failing_mkdir(self, *a, **k):
        raise PermissionError(13, "Permission denied", str(self))
    monkeypatch.setattr(pathlib.Path, "mkdir", failing_mkdir)
    with pytest.raises(OutputDirError, match=r"could not be created \(PermissionError\)"):
        create_run_dir(tmp_path / "out", scan, run_id="r1")


def test_created_directory_that_resolves_elsewhere_is_rejected(make_project, tmp_path, monkeypatch):
    """N-7: the post-creation check compares the created directory's resolved path with the
    expected one (e.g. swapped for a junction right after mkdir), not only is_dir()."""
    import pathlib
    scan = scan_project(make_project())
    out = (tmp_path / "out").resolve()
    real = pathlib.Path.resolve

    def resolve_after_swap(self, strict=False):
        if strict and self.name == "r1" and self.parent.name == "TEST-1":
            return out / "OTHER-9" / "r1"
        return real(self, strict=strict)
    monkeypatch.setattr(pathlib.Path, "resolve", resolve_after_swap)
    with pytest.raises(OutputDirError, match="not created as a regular directory at the expected path"):
        create_run_dir(out, scan, run_id="r1")


def test_created_directory_check_is_case_exact(make_project, tmp_path, monkeypatch):
    """N-4/N-7: a post-creation resolution differing only by case is refused, also on Windows
    where Path equality ignores case."""
    import pathlib
    scan = scan_project(make_project())
    out = (tmp_path / "out").resolve()
    real = pathlib.Path.resolve

    def resolve_case_variant(self, strict=False):
        if strict and self.name == "r1" and self.parent.name == "TEST-1":
            return out / "test-1" / "r1"
        return real(self, strict=strict)
    monkeypatch.setattr(pathlib.Path, "resolve", resolve_case_variant)
    with pytest.raises(OutputDirError, match="not created as a regular directory at the expected path"):
        create_run_dir(out, scan, run_id="r1")


# ---- N-4: project IDs differing only by case never share an output directory

def test_case_variant_project_ids_cannot_share_output_dir_by_resolution(make_project, tmp_path, monkeypatch):
    """Any OS: resolution to a case variant of the literal path is refused (string compare)."""
    import pathlib
    scan = scan_project(make_project(project_id="TEST-1"))
    out = (tmp_path / "out").resolve()
    real = pathlib.Path.resolve

    def resolve_existing_lowercase(self, strict=False):
        if not strict and self.name == "r1" and self.parent.name == "TEST-1":
            return out / "test-1" / "r1"
        return real(self, strict=strict)
    monkeypatch.setattr(pathlib.Path, "resolve", resolve_existing_lowercase)
    with pytest.raises(OutputDirError, match="differs only by case"):
        create_run_dir(out, scan, run_id="r1")


def test_case_variant_project_ids_cannot_share_output_dir_on_real_fs(make_project, tmp_path):
    """Real filesystem: after project 'test-1' wrote out/test-1/, project 'TEST-1' is refused on a
    case-insensitive filesystem; on a case-sensitive one it gets its own directory."""
    from conftest import fs_is_case_insensitive
    out = tmp_path / "out"
    lower = scan_project(make_project(name="p_lower", project_id="test-1"))
    upper = scan_project(make_project(name="p_upper", project_id="TEST-1"))
    _, lower_dir = create_run_dir(out, lower, run_id="r1")
    if fs_is_case_insensitive(tmp_path):
        with pytest.raises(OutputDirError, match="differs only by case"):
            create_run_dir(out, upper, run_id="r2")
        assert [p.name for p in (out).iterdir()] == ["test-1"]
        assert [p.name for p in lower_dir.parent.iterdir()] == ["r1"]  # nothing written into it
    else:
        _, upper_dir = create_run_dir(out, upper, run_id="r2")
        assert upper_dir.parent != lower_dir.parent


def test_created_path_that_is_not_a_directory_is_rejected(make_project, tmp_path, monkeypatch):
    """What a Windows device name does: mkdir 'succeeds' but no directory exists."""
    import pathlib
    scan = scan_project(make_project())
    monkeypatch.setattr(pathlib.Path, "is_dir", lambda self: False)
    with pytest.raises(OutputDirError, match="not created as a regular directory"):
        create_run_dir(tmp_path / "out", scan, run_id="r1")
