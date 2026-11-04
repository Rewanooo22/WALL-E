# ADR-001 — Phase 1 Deterministic Baseline Architecture

| Field | Value |
|---|---|
| Status | **ACCEPTED — M0 (2026-11-04)** |
| Path | `docs/adr/ADR-001-phase1-deterministic-baseline.md` |
| Date | 2026-11-04 |
| Governs | Phase 1 (`docs/spec/phase-1-document-intelligence.md`) |
| Policy | PC-01 (ADR format with engineering explanation); NFR-ARCH-001 (≥ 2 alternatives, including a simpler baseline) |

---

## 1. Context

Phase 1 must turn a folder of project documents (text PDFs, PDF drawings with text layers, XLSX BOQs and registers) into an evidence-grounded report with six analysis sections. Every factual claim must be traceable to a file and page or cell. Conflicts must never be resolved silently. Confidential data must never leave the machine. No quantity take-off, cost, schedule, approval, maintenance or CAD-geometry work is in scope. Phase 1 is a CLI-based internal prototype.

## 2. Decision drivers

| ID | Driver | Source |
|---|---|---|
| DR-1 | Every claim traceable to source and independently re-checkable | [C] mandatory rule; FR-EVI-001 |
| DR-2 | No confidential data to external services | [C]; D-06; FR-SEC-001 |
| DR-3 | Deterministic processing separate from reasoning; reproducible output | [C]; D-10; NFR-REL-001 |
| DR-4 | Testable exactly against ground truth | NFR-ARCH-002 |
| DR-5 | Simplest architecture that meets the requirements; no unneeded frameworks | [C]; D-08; NFR-ARCH-001 |
| DR-6 | Usable on real confidential documents locally, once a deployment-level sandbox exists | [C] usable pipeline |
| DR-7 | Extensible to later phases (LLM reasoning, quantity, planning) without rework of the evidence model | [C] extensibility |

## 3. Options considered (overall architecture)

| Option | Description | DR-1 | DR-2 | DR-3 | DR-4 | DR-5 | Verdict |
|---|---|---|---|---|---|---|---|
| **O1 Deterministic batch pipeline** | Load → extract → identify → analyse → claims → verify → report; no LLM, no network | ✔ | ✔ by construction | ✔ | ✔ exact | ✔ | **Chosen** |
| O2 O1 + optional LLM stage | LLM writes the summary and observations, through an outbound gate | ✔ if verified | ✔ only for synthetic data; real documents blocked | partial | partial (non-deterministic) | ✗ adds adapter, gate and evaluation now | Deferred to a later phase |
| O3 Agent framework (e.g. Claude Agent SDK, LangGraph) with a tool-use loop | Model plans and calls extraction tools | depends | ✗ requires a model provider | ✗ | ✗ | ✗ | Rejected for Phase 1: there is no open-ended task to plan |
| O4 Retrieval-augmented generation with a vector store | Embed chunks; answer questions | ✔ partial | ✗ | ✗ | ✗ | ✗ | Rejected: Phase 1 matches exact identifiers, not semantic queries; the output is a fixed report, not Q&A |

**Engineering explanation.** An agent framework or vector search is valuable when the system must decide *what to look for* in an open-ended question. Phase 1 has a fixed job: extract, cross-check and report. Every step can be written as an explicit rule, so a model would only add non-determinism, cost and a confidentiality problem. Keeping Phase 1 deterministic also creates a **reliable evidence layer**: when a later phase adds LLM reasoning, the model can only cite evidence this layer produced, and the same verifier checks it.

## 4. Sub-decisions

### 4.1 PDF extraction library
| Option | Notes | Licence | Verdict |
|---|---|---|---|
| **pdfplumber 0.11.10** (built on pdfminer.six) | Word positions, tables, page geometry; pure Python | MIT | **Chosen** (primary extractor) |
| pypdf | Good text and metadata; weaker layout and tables | BSD | Not needed |
| PyMuPDF | Fast and capable | **AGPL** / commercial | Rejected: the licence is incompatible with an internal tool unless a commercial licence is purchased |
| pdfminer.six directly | Lower level; pdfplumber already wraps it | MIT | Not needed |

### 4.2 Excel extraction library
| Option | Verdict |
|---|---|
| **openpyxl 3.1.5** | **Chosen**: cell-level access, merged ranges, hidden flags, number formats, cached formula values (`data_only=True`) |
| pandas | Rejected: table-oriented; loses cell addresses, formatting and merge information needed for citations |

### 4.3 Citation resolver engine (independence)
| Option | Verdict |
|---|---|
| Look up the pipeline's own evidence store | Rejected: circular, catches nothing |
| Re-extract with the same libraries | Rejected as the only check: catches pipeline bugs only |
| **Re-extract with a different engine**: pypdfium2 (PDFium) for PDF; stdlib `zipfile` + `xml.etree` for XLSX | **Chosen**: no new dependency (pypdfium2 comes with pdfplumber); different code paths. Limitations in spec §13.2 |
| Human review only | Kept as a completion criterion (spot-check), not as the main mechanism |

### 4.4 Data models
| Option | Verdict |
|---|---|
| **pydantic 2.13.5** | **Chosen**: schema validation of manifest, evidence, claims and report; JSON schema export for the report |
| dataclasses + hand-written validation | Simpler dependency profile but more custom code to get validation right; rejected |

### 4.5 Parser isolation
| Option | Verdict |
|---|---|
| In-process parsing | Rejected: one malformed file can hang or crash the whole run |
| **Per-file worker subprocess** (`multiprocessing` spawn) with timeout and `resource` limits | **Chosen** for fault containment. Stated explicitly as **not** a security sandbox |
| OS-level sandbox (network namespace, seccomp, container with `--network=none`, unprivileged user) | Out of Phase 1 code; **required deployment mode for non-synthetic documents** (spec §14.2). Implementing it portably is environment-specific |

### 4.6 Storage and state
| Option | Verdict |
|---|---|
| **Immutable run directory** with JSON files (`report.json`, `report.md`, `run_manifest.json`) | **Chosen**: no sessions or case files are needed for batch analysis |
| SQLite / database | Rejected: no query workload; adds migration burden |

### 4.7 Interface
| Option | Verdict |
|---|---|
| **CLI** (`python -m wall_e analyze <project_dir> --out <dir>`) | **Chosen**: internal prototype; scriptable for evaluation |
| Web UI / API server | Out of Phase 1 scope ([C]) |

### 4.8 LLM and outbound gate
**Not built in Phase 1.** No outbound path exists, so a gate would guard nothing. FR-SEC-002 becomes mandatory in the phase that first adds an outbound call. Static and runtime tests (spec INV-05) prove no network path exists in Phase 1.

## 5. Decision

Adopt **O1**, with sub-decisions 4.1–4.8.

**Runtime dependencies** (already installed in the development environment; to be pinned):
- `pdfplumber==0.11.10` (pulls in `pdfminer.six` and `pypdfium2`)
- `openpyxl==3.1.5`
- `pydantic==2.13.5`

**Development-only dependencies:**
- `pytest` (not installed; installation requires approval)
- `reportlab==5.0.1`, used for synthetic fixture generation only

**Not used:** pypdf, pandas, PyMuPDF, OCR engines, any LLM SDK, any web framework.

## 6. Test fixture variation matrix (summary; detailed in `tests/fixtures/fixture_spec.md` at M2)

| Category | Variations |
|---|---|
| Title blocks | ≥ 3 layouts (bottom-right table; labelled fields in free layout; a rotated landscape sheet) |
| Revision schemes | letters (A, B, C), numbers (0, 1, 2), prefixed (P1 → C1); a revision table with dates |
| PDF text | multi-column specification; table split across pages; hyphenation and ligatures; page with no text layer (image only); page with an unreliable text layer, if one can be generated (font without a Unicode mapping — feasibility checked in M2) |
| XLSX | merged cells; formula with cached value; formula without a cached value; hidden sheet and row; dates stored as serial numbers; multi-row header; pricing columns present |
| Attributes | synonyms; qualifiers; gauge vs absolute; ambiguous units; mixed SI / US customary |
| Identity | same document number in two projects; duplicate file (same hash); same number and revision with different content |
| Files | unsupported type; encrypted PDF; oversized file; zip-bomb XLSX; file that hangs or crashes the parser (where it can be safely constructed) |
| Controls | clean negative-control documents with no planted issues |
| Security | injected-instruction text; Markdown and HTML in document text |
| Responsibility | Piping documents present but Piping not in `contracted_scope`; `contracted_scope` absent; each `delivery_model` value and an invalid value |

## 7. Consequences

**Positive**
- Exact, reproducible, offline results; the confidentiality requirement holds by construction.
- Exact acceptance testing against ground truth.
- The evidence and claim model is a stable foundation for later phases.

**Negative / accepted**
- No semantic reading of free text: free-text conflicts and technical judgement are out of reach. Section 6 is limited to the explicit cross-document rules (spec §10).
- Heuristic identification (title blocks, headers) may fail on real layouts not covered by the fixtures; such failures surface as UNRESOLVED or AMBIGUOUS, not as wrong facts.
- Parser isolation is fault containment only; real documents need a deployment-level sandbox.

## 8. Risks
| Risk | Mitigation |
|---|---|
| Overfitting to self-made fixtures | Variation matrix; blind holdout protocol (spec §15.2); results reported as synthetic only |
| Shared blind spots between the extractor and the resolver | Different engines; stated limits (spec §13.2); human spot-check |
| Parser vulnerabilities in pdfminer.six, PDFium or openpyxl | Pinned versions; trusted-source rule; deployment sandbox required for real documents |
| Glossary or pattern defaults mistaken for company conventions | Labelled [A]; user review in M0; manifest overrides in a later schema version |

## 9. Revisit triggers
- A requirement for open-ended questions, semantic conflict detection or generated narrative → evaluate O2 (and the outbound gate) with an ADR.
- Document volumes where full re-extraction becomes too slow → evaluate caching or an index.
- Holdout or real-document results showing the identification heuristics are insufficient → evaluate layout-aware extraction approaches.
- A requirement to process scanned documents → separate OCR ADR with its own evaluation.

## 10. Engineering explanation (summary)
The core idea is to **separate what the documents say from what WALL-E concludes, and to make both checkable.** Extraction produces evidence items with exact locations. Analysis rules turn evidence into claims, using templates so every value in a sentence has a known source. A second, independent extraction engine re-reads every cited location to confirm the quote is really there. Nothing in this chain is "intelligent", and that is deliberate. For engineering documents, a system that says "UNKNOWN: two sources disagree" correctly is more valuable than one that guesses fluently. Intelligence can be layered on later, on top of evidence that has already earned trust.
