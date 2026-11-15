# WALL-E

*Workflow Automation & Logic for Learning Engineering*

WALL-E is an internal, evidence-grounded, multi-discipline engineering and project execution assistant, in early development. Its initial scope is **deterministic document intelligence** on engineering project documents, for the Mechanical, Piping, Fabrication, Installation, and Electrical & Instrumentation (E&I) disciplines. Phase 1 is specified as a CLI-based internal prototype that is read-only and advisory. Given a project folder with a `project.json` manifest and its PDF and XLSX documents, it is meant to produce a report in which every factual claim cites its source evidence. Phase 1 uses no LLM or network access and makes no engineering approvals.

> **Status: early development (Phase 1, milestone M1 of M1–M7).**
> Most of the project currently exists as specification. The implemented code covers project loading (manifest validation, safe file discovery, hashing, classification), the core data models and the run manifest. **There is no CLI yet, and no PDF or XLSX parsing, analysis or report generation.**

## What is implemented vs. specified

| Area | State | Where |
|---|---|---|
| Manifest loading and validation (`project.json`) | **Implemented** | `src/wall_e/project.py` |
| Safe file discovery, SHA-256 hashing, magic-byte checks, classification, duplicate detection | **Implemented** | `src/wall_e/project.py` |
| Core data models (manifest, file records, evidence, claims) | **Implemented** (structural validation only) | `src/wall_e/models.py` |
| Run directory and reproducible run manifest | **Implemented** | `src/wall_e/run.py` |
| Static check that the source has no network or LLM SDK imports | **Implemented** (test) | `tests/test_static_policy.py` |
| PDF extraction (text, words, tables) and XLSX extraction (cells) in isolated worker processes | Specified, not implemented | Phase 1 spec §12, §14 |
| Document identification, register reconciliation, missing-information / revision / conflict rules, BOQ transcription | Specified, not implemented | Phase 1 spec §8–§10 |
| Claim rendering, rule checks and independent citation resolver | Specified, not implemented | Phase 1 spec §11, §13 |
| Report output (`report.json`, `report.md`) | Specified, not implemented | Phase 1 spec §7, §12 |
| CLI (`python -m wall_e analyze <project_dir> --out <dir>`) | Specified, not implemented | ADR-001 §4.7 |
| Synthetic fixtures, blind holdout and evaluation | Specified, not implemented | Phase 1 spec §15–§16 |

The runtime dependencies `pdfplumber` and `openpyxl` are pinned in `pyproject.toml` for the planned extraction stages. No current module uses them.

## Implemented components (M1)

### `wall_e.project`: project loading

- **`load_manifest(project_dir)`** reads and validates `project.json` (size limit of 1 MB, UTF-8 with an optional BOM). It returns the parsed `ProjectManifest` and the manifest's SHA-256.
  - Fatal problems (a missing or unparsable manifest, an invalid `project_id`, an unsupported `schema_version`) raise `ManifestError`.
  - Every other problem is recorded as a `ManifestIssue`. The dependent feature then degrades to UNKNOWN or "not evaluated" instead of guessing.
- **`scan_project(project_dir, limits=Limits())`** returns a `ProjectScan` with one `FileRecord` per discovered file, sorted by relative POSIX path:
  - **Containment on resolved paths.** Symlinks, Windows junctions and other reparse points that leave the project root are recorded as `REJECTED_PATH`, and they are never traversed or hashed.
  - **Fault tolerance.** A filesystem error on one entry is recorded as `UNREADABLE` with the error class only, and the scan continues.
  - **Type and size checks.** `.pdf` and `.xlsx` files are checked against their magic bytes, and the per-file size limit (`Limits.max_file_bytes`, default 200 MB) is enforced. Other types are recorded as unsupported, never skipped silently.
  - **Hashing and duplicates.** Each file gets a SHA-256 hash, and content duplicates are marked.
  - **Classification.** Each file gets a classification (`synthetic`, `public-licensed`, `confidential`) taken from its manifest entry or the manifest default, and falling back to `confidential`. Conflicting declarations resolve to the most restrictive. Classifications are path-specific.

### `wall_e.models`: data contracts

Strict Pydantic v2 models and enums shared by the pipeline stages. They cover:

- the manifest: `ProjectManifest`, `ContractedScope`, `Conventions`;
- file records: `FileRecord`, plus the Coverage statuses in `FileStatus`;
- evidence and claims: `Locator`, `Evidence`, `EvidenceLink`, `Claim`, with epistemic classes and evidence tiers.

Evidence IDs are deterministic and namespaced by `project_id` (`make_evidence_id`). The models perform structural validation only; semantic verification is planned for a later milestone.

### `wall_e.run`: run manifest

- **`create_run_dir(out_root, scan, run_id=None)`** creates a new, immutable `out_root/<project_id>/<run_id>/` directory. It refuses output locations inside the project, ancestors of the project, and paths that escape `out_root`.
- **`build_run_manifest(...)`** records the input hashes, the WALL-E, Python and dependency versions, a configuration hash and the manifest issues.
- **`write_run_manifest(...)`** writes the manifest and never overwrites an existing one.
- **`stable_view(...)`** drops the fields that legitimately vary between runs (`run_id`, `started_at`).

### Example

There is no CLI yet. The implemented stage can be called from Python:

```python
from pathlib import Path
from wall_e.project import Limits, scan_project
from wall_e.run import build_run_manifest, create_run_dir, write_run_manifest

scan = scan_project(Path("path/to/project"))        # requires path/to/project/project.json
for rec in scan.files:
    print(rec.rel_path, rec.status.value, rec.classification.value)

run_id, run_dir = create_run_dir(Path("out"), scan)
write_run_manifest(run_dir, build_run_manifest(scan, Limits(), run_id))
```

The manifest format is defined in the [Phase 1 specification §4.2](docs/spec/phase-1-document-intelligence.md).

## Getting started

### Prerequisites

- Python 3.11 or later (`requires-python = ">=3.11"`)

### Installation

```bash
git clone https://github.com/Rewanooo22/wall-e.git
cd wall-e
python -m venv .venv
source .venv/bin/activate          # Windows: Git Bash: source .venv/Scripts/activate
                                   #          PowerShell: .venv\Scripts\Activate.ps1
                                   #          cmd: .venv\Scripts\activate.bat
pip install -e ".[dev]"
```

The `dev` extra installs `pytest` and `reportlab` (reportlab is reserved for synthetic fixture generation). The runtime dependencies are pinned: `pdfplumber==0.11.10`, `openpyxl==3.1.5`, `pydantic==2.13.5`.

### Running the tests

```bash
pytest
```

`pyproject.toml` configures `pythonpath = ["src"]` and `testpaths = ["tests"]`. The suite contains 106 test functions across five files, several of them parametrised. Several tests depend on platform features and skip where those are unavailable: symlink creation privileges, Windows junctions, ACLs and case-sensitive directories, hard links, and POSIX permissions.

| Test file | Covers |
|---|---|
| `tests/test_manifest.py` | Manifest parsing, validation and issue reporting |
| `tests/test_discovery.py` | File discovery, path containment, hashing, classification matching, duplicates |
| `tests/test_models.py` | Data-model validation |
| `tests/test_run_manifest.py` | Run directory safety and run manifest contents |
| `tests/test_static_policy.py` | No network or LLM SDK module imports in `src/wall_e` (static import check; `subprocess` is not checked) |

## Project structure

```
wall-e/
├── .gitignore
├── CLAUDE.md                        # Working instructions for Claude Code sessions
├── pyproject.toml
├── CURRENT_STATE.md                 # Detailed development log and open review findings
├── docs/
│   ├── spec/
│   │   ├── phase-1-document-intelligence.md   # Governing Phase 1 specification (approved)
│   │   ├── 01-agent-charter.md                # v0.1 draft (Phase 0)
│   │   ├── 02-requirements.md                 # v0.1 draft (Phase 0)
│   │   └── 03-capabilities-boundaries.md      # v0.1 draft (Phase 0)
│   └── adr/
│       └── ADR-001-phase1-deterministic-baseline.md   # Accepted architecture decision
├── src/wall_e/
│   ├── __init__.py                  # __version__ = "0.1.0"
│   ├── models.py
│   ├── project.py
│   └── run.py
└── tests/
    ├── conftest.py
    ├── test_discovery.py
    ├── test_manifest.py
    ├── test_models.py
    ├── test_run_manifest.py
    └── test_static_policy.py
```

## Design documents

- [Phase 1 specification: Multi-discipline Document Intelligence](docs/spec/phase-1-document-intelligence.md) (approved at M0). Covers inputs and the manifest, report sections, deterministic analysis rules, the evidence and claim model, the processing pipeline, verification, security and isolation, the dataset and holdout protocol, and acceptance criteria.
- [ADR-001: Phase 1 deterministic baseline architecture](docs/adr/ADR-001-phase1-deterministic-baseline.md) (accepted). Records the library choices, parser isolation, storage, the CLI interface and the decision to have no LLM or outbound path in Phase 1.
- [01: Agent charter](docs/spec/01-agent-charter.md), [02: Requirements](docs/spec/02-requirements.md) and [03: Capabilities and boundaries](docs/spec/03-capabilities-boundaries.md) are v0.1 drafts. Where they conflict with the Phase 1 specification, the specification governs.
- [CURRENT_STATE.md](CURRENT_STATE.md) is the development log: milestone status, review findings, deferred items and known risks.

## Planned Phase 1 pipeline (specified, not implemented)

The pipeline below is summarised from Phase 1 spec §12. Only step 1 exists today.

1. **Load**: validate the manifest, discover files, contain paths, hash, classify, detect duplicates. **(implemented in M1)**
2. **Extract**: per-file isolated worker processes for PDF (page text, word boxes, tables) and XLSX (cells and flags).
3. **Identify**: document number, revision, title, date, status and discipline.
4. **Analyse**: register reconciliation, revision issues, missing information, attribute conflicts, BOQ transcription, observations.
5. **Claims**: template rendering into claim objects.
6. **Verify**: rule checks (V-01..V-08) plus an independent citation resolver.
7. **Report**: `report.json`, `report.md` and `run_manifest.json` under `out/<project_id>/<run_id>/`.

## Limitations

- **Pre-alpha.** Only the loading stage, data models and run manifest exist. Nothing can analyse documents yet.
- **Synthetic data only.** Development uses synthetic data, and the project's process rule forbids real or confidential documents in development sessions.
- **Isolation is not a sandbox.** The planned per-file subprocess isolation is fault containment only, not security isolation. A crafted PDF or XLSX file could exploit a parser vulnerability and run code with the user's privileges, including network access. See the required operating mode below.
- **Known open findings.** Open review findings and deferred risks (for example, check-then-use windows and hard links to files outside the project) are tracked in `CURRENT_STATE.md`.

## Required operating mode for non-synthetic documents

Phase 1 is **not** a hardened sandbox, and its code does not implement one (Phase 1 spec §14.2).

- **Deployment-level isolation is required** before WALL-E processes any non-synthetic document. Examples are a no-network namespace, an unprivileged user, a read-only filesystem, seccomp, or a container started with `--network=none`.
- **Trusted sources only.** Phase 1 is intended only for documents from trusted sources.
- **Pinned dependencies, kept up to date.** Dependencies are pinned in `pyproject.toml`, and the pins must be kept up to date.
- **No real or confidential documents in cloud development sessions** (Phase 1 spec §14.4). Development and testing use synthetic data only.

## Roadmap

The specified next milestone (M2) covers the fixture specification, the sealed blind holdout and the development fixture generator. Parsers, analysis, verification and reporting follow in M3–M7, as defined in the Phase 1 specification.
