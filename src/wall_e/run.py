"""Run directory and run manifest (spec §12 step 7; ADR-001 §4.6).

Every run writes to a new, immutable directory: out/<project_id>/<run_id>/.
The run manifest records everything needed to reproduce the run: input hashes,
tool and dependency versions, configuration hash. Only run_id and started_at
vary between identical runs (spec INV-08).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import wall_e
from wall_e.project import Limits, ProjectScan

TRACKED_DISTRIBUTIONS = ("pdfplumber", "pdfminer.six", "pypdfium2", "openpyxl", "pydantic")
RUN_MANIFEST_NAME = "run_manifest.json"
VOLATILE_KEYS = frozenset({"run_id", "started_at"})


class OutputDirError(Exception):
    pass


def dependency_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for dist in TRACKED_DISTRIBUTIONS:
        try:
            out[dist] = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            out[dist] = "not installed"
    return out


def config_hash(limits: Limits) -> str:
    payload = json.dumps({"limits": asdict(limits)}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def create_run_dir(out_root: Path, scan: ProjectScan, run_id: str | None = None) -> tuple[str, Path]:
    """Create out_root/<project_id>/<run_id>/. Refuses to write inside the project
    root (outputs would be rediscovered as inputs) or into an existing run dir."""
    out_root = Path(out_root).resolve()
    try:
        out_root.relative_to(scan.root)
        raise OutputDirError("output directory must not be inside the project directory")
    except ValueError:
        pass
    run_id = run_id or uuid.uuid4().hex
    run_dir = out_root / scan.manifest.project_id / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise OutputDirError(f"run directory already exists: {run_dir}") from exc
    return run_id, run_dir


def build_run_manifest(scan: ProjectScan, limits: Limits, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project_id": scan.manifest.project_id,
        "wall_e_version": wall_e.__version__,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "dependencies": dependency_versions(),
        "config_sha256": config_hash(limits),
        "manifest_sha256": scan.manifest_sha256,
        "inputs": [
            {"path": r.rel_path, "sha256": r.sha256, "size_bytes": r.size_bytes,
             "status": r.status.value, "classification": r.classification.value}
            for r in scan.files
        ],
        "manifest_issues": [i.model_dump() for i in scan.manifest.issues],
    }


def write_run_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    path = Path(run_dir) / RUN_MANIFEST_NAME
    if path.exists():
        raise OutputDirError(f"{path} already exists; run outputs are immutable")
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def stable_view(manifest: dict[str, Any]) -> dict[str, Any]:
    """The run manifest without fields that legitimately vary between runs."""
    return {k: v for k, v in manifest.items() if k not in VOLATILE_KEYS}
