"""Shared helpers for M1 tests. Files here are minimal byte stubs with valid
signatures; real synthetic documents arrive with the M2 fixture generator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PDF_STUB = b"%PDF-1.7\n% stub for discovery tests only\n%%EOF\n"
XLSX_STUB = b"PK\x03\x04stub-for-discovery-tests-only"


def write_manifest(root: Path, **fields) -> Path:
    data = {"schema_version": "1.0", "project_id": "TEST-1"}
    data.update(fields)
    root.mkdir(parents=True, exist_ok=True)
    p = root / "project.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def make_project(tmp_path):
    def _make(name: str = "proj", contents: dict[str, bytes] | None = None, **manifest_fields) -> Path:
        root = tmp_path / name
        write_manifest(root, **manifest_fields)
        for rel, content in (contents or {}).items():
            fp = root / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(content)
        return root
    return _make
