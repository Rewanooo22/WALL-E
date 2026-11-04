# WALL-E — Current State

_Last updated: 2026-11-04_

## Product (confirmed)
WALL-E is an internal, evidence-grounded, multi-discipline engineering and project execution assistant. Initial scope: document intelligence across Mechanical, Piping, Fabrication, Installation, and E&I. Read-only and advisory; no engineering approvals.

## Current phase
**Phase 1 — Multi-discipline Document Intelligence.** M0 approved and committed (`fd3816c`). **M1 implemented, awaiting review (not committed).**

## Governing documents
- `docs/spec/phase-1-document-intelligence.md`: governs Phase 1 (approved).
- `docs/adr/ADR-001-phase1-deterministic-baseline.md`: accepted. Deterministic CLI pipeline; no LLM, network, agent framework, vector search or database.
- `docs/spec/01–03` v0.1: carry a Phase 1 precedence banner. Maintenance-specific items are inactive; cross-cutting requirements remain in force (Phase 1 spec §17). A v0.2 rewrite is planned after Phase 1.

## Completed
- `CLAUDE.md` routing policy (`c082477`).
- Specs 01–03 v0.1 draft checkpoint (`cd38a21`).
- Product redirection analysis (project execution focus).
- M0: Phase 1 spec, ADR-001, banners on 01–03 (`fd3816c`).
- M1 (uncommitted): `pyproject.toml`, `.gitignore`, `src/wall_e/{models,project,run}.py`; tests for manifest, discovery, models, run manifest, static network policy. 45 tests pass; 4 of 4 deliberate code mutations caught by the tests.

## Approved M0 decisions
- S-1 standalone Phase 1 spec; S-2 five claim classes ("Fact as stated in source" display); S-3 BOQ source transcription only; S-4 fully deterministic.
- `delivery_model` and `contracted_scope` manifest fields; execution responsibility never inferred.
- Conventions come only from the project manifest; Appendix B default vocabularies (generic, labelled assumptions).
- Explicit observation rules OBS-01..07; forbidden-phrase check.
- Cross-unit tolerance 1%; ambiguous units not comparable; text-quality thresholds (2% / 5 words).
- Independent resolver engines (PDFium; stdlib XLSX); stated limitations.
- Per-file subprocess = fault containment, not a sandbox; a deployment sandbox is required for non-synthetic documents.
- Blind holdout protocol and size; metrics always n/N; provisional holdout thresholds.
- Completion criteria incl. 30-citation human spot-check.
- pytest installation (dev only) approved for M1.
- Process rule: **no real or confidential documents in the cloud development session.**

## Open questions
- Q-P1-01..04 (Phase 1 spec §18); CQ-01..13 from the change proposal (company confirmation).

## Known risks / limitations
- Synthetic validation only; not evidence of real-world reliability.
- Holdout author is the same model family (correlated blind spots).
- Approval gates are not technically enforced (deferred by user).

## Next step
Await review of M1. Next: **M2**: fixture spec, then the blind holdout **before** any parser code or dev ground truth, then the dev fixture generator.
