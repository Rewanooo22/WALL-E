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
import re
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
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")  # used with fullmatch
# L-3: Windows device names. Path components are limited to [A-Za-z0-9_-], so only the
# bare names (case-insensitive) can occur. Module-level so tests can enable it on any OS.
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(10)})
WINDOWS_RESERVED_NAMES_APPLY = sys.platform == "win32"


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


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def create_run_dir(out_root: Path, scan: ProjectScan, run_id: str | None = None) -> tuple[str, Path]:
    """Create out_root/<project_id>/<run_id>/.

    The final run directory is resolved and refused if it is inside the scanned
    project (outputs would be rediscovered as inputs), is an ancestor of the
    project, or escapes out_root. Existing run directories are never reused."""
    run_id = uuid.uuid4().hex if run_id is None else run_id
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise OutputDirError("run_id must match ^[A-Za-z0-9_-]{1,64}$")
    if WINDOWS_RESERVED_NAMES_APPLY:
        for label, name in (("project_id", scan.manifest.project_id), ("run_id", run_id)):
            if name.upper() in WINDOWS_RESERVED_NAMES:
                raise OutputDirError(f"{label} {name!r} is a reserved device name on Windows")
    out_root = Path(out_root).resolve()
    literal = out_root / scan.manifest.project_id / run_id
    run_dir = literal.resolve()
    if run_dir == out_root or not _is_within(run_dir, out_root):
        raise OutputDirError("run directory escapes the output directory")
    if _is_within(run_dir, scan.root):
        raise OutputDirError("output directory must not be inside the project directory")
    if _is_within(scan.root, run_dir):
        raise OutputDirError("run directory must not be an ancestor of the project directory")
    # Exact string comparison: Path equality is case-insensitive on Windows (N-4).
    if str(run_dir) != str(literal):
        # L-2: a link/junction under out_root (e.g. out/<project_id> -> out/<other>) would
        # redirect this run into another project's outputs. N-4: on a case-insensitive
        # filesystem an existing out/test-1 would also take the outputs of project TEST-1.
        raise OutputDirError("run directory path resolves elsewhere (link or reparse point, "
                             "or an existing directory whose name differs only by case)")
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise OutputDirError(f"run directory already exists: {run_dir}") from exc
    except OSError as exc:
        raise OutputDirError(f"run directory could not be created ({type(exc).__name__})") from exc
    # L-3: confirm a real directory was created at exactly this path.
    try:
        ok = run_dir.is_dir() and str(run_dir.resolve(strict=True)) == str(literal)
    except (OSError, RuntimeError):
        ok = False
    if not ok:
        raise OutputDirError("run directory was not created as a regular directory at the expected path")
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
