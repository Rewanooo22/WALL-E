# WALL-E

**Workflow Automation & Logic for Learning Engineering**

WALL-E is an internal, evidence-grounded assistant for multi-discipline engineering and project execution. Its first scope is **document intelligence** across Mechanical, Piping, Fabrication, Installation, and Electrical & Instrumentation (E&I) project documents.

It is read-only and advisory. It never approves engineering work.

## Phase 1: deterministic document intelligence

Phase 1 is a command-line prototype. Given a project folder (a `project.json` manifest plus its documents), it will produce an evidence-grounded report with these sections:

1. Project Summary
2. Document Register
3. Discipline-based Scope Breakdown
4. Missing Information
5. Document Conflicts and Revision Issues
6. Preliminary Technical Observations
7. Coverage
8. Limitations

Design choices ([ADR-001](docs/adr/ADR-001-phase1-deterministic-baseline.md)):

- **Deterministic pipeline.** No LLM, network access, agent framework, vector search, or database.
- **Every claim cites its evidence** (file, page, cell).
- **Nothing is skipped silently.** Unsupported or unreadable files are reported under Coverage.
- **Reproducible runs.** Each run writes to its own immutable folder, `out/<project_id>/<run_id>/`, with a run manifest that records input hashes, tool and dependency versions, and a configuration hash.

### Supported inputs

| Type | Handling |
|---|---|
| Text-based PDF | Page text, word positions, tables |
| PDF drawings with a text layer | Title block fields, revision tables, text and tables (no geometry) |
| Excel `.xlsx` | Cell values with sheet and cell locators |

Scanned or image-only pages, `.xls`, `.docx`, DWG/DXF, images, and encrypted PDFs are listed as unsupported.

### Out of scope for Phase 1

Quantity take-off, cost estimation, scheduling, design approval or code-compliance judgements, CAD geometry, OCR, and any user interface or API. The full list is in [the Phase 1 spec](docs/spec/phase-1-document-intelligence.md#3-phase-1-non-goals).

## Status

Work is split into milestones:

- **M0** (done): Phase 1 spec and ADR-001.
- **M1** (merged into `main`): project manifest parsing, file discovery and classification, data models, and the run manifest, with tests.
- **M2 onward**: document extraction and report generation. Not started yet.

There is no end-to-end report command yet. See [CURRENT_STATE.md](CURRENT_STATE.md) for the detailed status, open review findings, and next steps.

## Getting started

Requires Python 3.11+.

```bash
git clone https://github.com/Rewanooo22/wall-e.git
cd wall-e
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Some tests cover Windows-only path behaviour (NTFS case rules, 8.3 short names) and are skipped on other platforms.

## Repository layout

```text
wall-e/
├── src/wall_e/
│   ├── models.py      # Data models (pydantic)
│   ├── project.py     # project.json manifest parsing and file discovery
│   └── run.py         # Run folder and run manifest
├── tests/             # pytest suite
├── docs/
│   ├── spec/          # Agent charter, requirements, capabilities, Phase 1 spec
│   └── adr/           # Architecture decision records
├── CURRENT_STATE.md   # Detailed progress log
└── pyproject.toml
```

## Documentation

- [Phase 1 spec](docs/spec/phase-1-document-intelligence.md): governs Phase 1
- [ADR-001: Phase 1 deterministic baseline](docs/adr/ADR-001-phase1-deterministic-baseline.md)
- [Agent charter](docs/spec/01-agent-charter.md), [requirements](docs/spec/02-requirements.md), [capabilities and boundaries](docs/spec/03-capabilities-boundaries.md) (v0.1 drafts; the Phase 1 spec takes precedence where they conflict)
