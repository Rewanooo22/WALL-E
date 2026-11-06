"""Shared helpers for M1 tests. Files here are minimal byte stubs with valid
signatures; real synthetic documents arrive with the M2 fixture generator."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PDF_STUB = b"%PDF-1.7\n% stub for discovery tests only\n%%EOF\n"
XLSX_STUB = b"PK\x03\x04stub-for-discovery-tests-only"


ERROR_PRIVILEGE_NOT_HELD = 1314  # Windows: symlink creation needs a privilege/Developer Mode


def symlink_privilege_missing(exc: BaseException) -> bool:
    """True only for 'this user/platform may not create symlinks', never for test bugs
    such as FileExistsError or a wrong path (T6)."""
    if isinstance(exc, NotImplementedError):
        return True
    if not isinstance(exc, OSError):
        return False
    if sys.platform == "win32":
        return getattr(exc, "winerror", None) == ERROR_PRIVILEGE_NOT_HELD
    return exc.errno == errno.EPERM


def symlink_or_skip(target: Path, link: Path, is_dir: bool = False) -> None:
    """Create a symlink, skipping the test only if symlink creation is not permitted."""
    try:
        os.symlink(target, link, target_is_directory=is_dir)
    except (OSError, NotImplementedError) as exc:
        if symlink_privilege_missing(exc):
            pytest.skip(f"symlink creation not permitted here: {type(exc).__name__}")
        raise


def junction_or_skip(target: Path, link: Path) -> None:
    """Create an NTFS directory junction (Windows; no admin rights needed)."""
    if sys.platform != "win32":
        pytest.skip("NTFS junctions are Windows-only")
    res = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                         capture_output=True, text=True)
    if res.returncode != 0 or not link.exists():
        pytest.skip(f"junction creation failed: {res.stdout.strip() or res.stderr.strip()}")


def dir_link_or_skip(target: Path, link: Path) -> None:
    """A directory link of whichever kind this platform allows."""
    if sys.platform == "win32":
        junction_or_skip(target, link)
    else:
        symlink_or_skip(target, link, is_dir=True)


def hardlink_or_skip(target: Path, link: Path) -> None:
    """Create a hard link, skipping only if the filesystem/platform cannot (test bugs such
    as a missing target or an existing link still raise)."""
    try:
        os.link(target, link)
    except (FileExistsError, FileNotFoundError):
        raise
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"hard link creation not supported here: {type(exc).__name__}")


def fs_is_case_insensitive(directory: Path) -> bool:
    """Ask the filesystem itself whether `directory` resolves names case-insensitively."""
    probe = directory / "case_probe.tmp"
    probe.write_bytes(b"")
    try:
        return (directory / "CASE_PROBE.TMP").exists()
    finally:
        probe.unlink()


def case_sensitive_dir_or_skip(path: Path) -> Path:
    """An empty directory in which names differing only by case are distinct files.
    Windows: NTFS per-directory case sensitivity via fsutil (skipped only if fsutil
    refuses). Elsewhere: a plain directory, skipped if the filesystem folds case."""
    path.mkdir(parents=True)
    if sys.platform == "win32":
        res = subprocess.run(["fsutil.exe", "file", "setCaseSensitiveInfo", str(path), "enable"],
                             capture_output=True, text=True)
        if res.returncode != 0:
            pytest.skip(f"fsutil setCaseSensitiveInfo unavailable: {(res.stdout or res.stderr).strip()}")
    if fs_is_case_insensitive(path):
        pytest.skip("could not obtain a case-sensitive directory")
    return path


@contextlib.contextmanager
def windows_special_names(directory: Path, names: dict[str, bytes]):
    """Create files whose names the Win32 layer would alter (trailing dot or space) via
    extended-length paths, and remove them the same way afterwards: pytest's own cleanup
    uses Win32 paths and could not. A failed removal fails the test (never ignored)."""
    if sys.platform != "win32":
        pytest.skip("Windows-only special names")
    base = "\\\\?\\" + str(directory.resolve()) + "\\"
    created = []
    try:
        for name, data in names.items():
            with open(base + name, "xb") as fh:
                fh.write(data)
            created.append(name)
        yield
    finally:
        failures = []
        for name in created:
            try:
                os.remove(base + name)
            except OSError as exc:
                failures.append(f"{name!r}: {exc!r}")
        if failures:
            pytest.fail("special-name files could not be removed: " + "; ".join(failures))


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


@contextlib.contextmanager
def windows_access_denied(path: Path):
    """Deny the current user read-data / list-directory access to `path` via an explicit
    ACL deny entry (icacls; no admin needed), then remove it. Windows-only.

    Only (RD) is denied (N-2): a full (F) deny also takes away the owner's ability to
    change the ACL back, leaving files that pytest cannot delete. A failed restore, or a
    path still unreadable after the restore, fails the test; it is never ignored."""
    if sys.platform != "win32":
        pytest.skip("Windows ACL test")
    user = os.environ.get("USERNAME")
    if not user:
        pytest.skip("USERNAME not set")
    res = subprocess.run(["icacls", str(path), "/deny", f"{user}:(RD)"], capture_output=True, text=True)
    if res.returncode != 0:
        pytest.skip(f"icacls deny failed: {res.stdout.strip() or res.stderr.strip()}")
    try:
        yield
    finally:
        restore = subprocess.run(["icacls", str(path), "/remove:d", user], capture_output=True, text=True)
        if restore.returncode != 0:
            pytest.fail(f"icacls restore failed (exit {restore.returncode}) for {path}: "
                        f"{restore.stdout.strip() or restore.stderr.strip()}")
        try:
            if path.is_dir():
                os.listdir(path)
            else:
                path.read_bytes()
        except OSError as exc:
            pytest.fail(f"{path} still not accessible after ACL restore: {exc!r}")
