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
