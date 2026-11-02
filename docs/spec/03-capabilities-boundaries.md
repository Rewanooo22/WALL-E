# 03 — WALL-E Capabilities and Boundaries

| Field | Value |
|---|---|
| Status | **DRAFT — awaiting user review** |
| Phase | 0 — Product Definition & Architecture |
| Depends on | 01-agent-charter, 02-requirements |
| Feeds | 04-agent-architecture, 05-tools-interfaces, 06-reasoning-workflows, 09-safety-boundaries, 11-evaluation-acceptance, 12-roadmap |

---

## 1. Purpose

This document turns the requirements in 02 into a **capability map**: the distinct things WALL-E can do, what each needs, how mature it must be in which phase, and where WALL-E's responsibility **stops**. It also lists the supporting components that capabilities depend on. These are named by *function* only, because technology choices belong to ADRs in 04 (D-08).

> **Engineering explanation.** A *requirement* says what must be true. A *capability* groups requirements into a coherent unit of behaviour that can be built, evaluated, and matured on its own. The roadmap (12) is then expressed as capability maturity, not as a list of features. Boundaries are written down as carefully as capabilities. For a safety-relevant agent, what it refuses to do is part of the design, not an afterthought.

---

## 2. Competency areas

The five competencies named in the project scope map to capabilities as follows:

| Competency | Capabilities |
|---|---|
| Understanding industrial facilities and equipment | CAP-01 |
| Understanding engineering documents | CAP-02 |
| Understanding process relationships | CAP-03 |
| Understanding maintenance history | CAP-04 |
| Failure investigations | CAP-06 (orchestrating CAP-01–05, 07–10) |

The cross-cutting capabilities CAP-05 and CAP-07 to CAP-10 implement the separation of concerns (D-10), epistemic discipline (D-12), memory (D-09), and auditability.

---

## 3. Capability catalogue

Maturity levels: **L0** not present · **L1** works on SRF happy paths · **L2** meets provisional thresholds on the full SRF evaluation set, including adversarial cases · **L3** meets thresholds on licence-cleared public data (later).

Concern type refers to D-10: **DET** deterministic computation, **RET** retrieval, **LLM** reasoning, **VER** verification.

### CAP-01 — Asset identification and context
| Field | Content |
|---|---|
| Does | Resolves a tag/description to one asset; returns hierarchy, attributes, redundancy, criticality (if recorded). |
| Concern type | RET (lookup), DET (hierarchy walk), LLM (only to interpret free-form user references, then confirmed by exact lookup). |
| Inputs | Structured asset data. |
| Outputs | Asset context evidence items (T1). |
| Requirements | FR-INT-002, FR-AST-001/002/003, FR-ING-001 |
| Target maturity | L2 in the first capability phase. |

### CAP-02 — Document retrieval and comprehension (text-based)
| Field | Content |
|---|---|
| Does | Finds relevant passages in text-based documents; handles revisions and conflicts; returns passages with precise locations. LLM reasoning interprets passages, but retrieval returns source text unaltered. |
| Concern type | RET (search), DET (revision rules, metadata filters), LLM (relevance judgement, interpretation). |
| Inputs | Text-based documents with metadata (A-05). |
| Outputs | Document evidence items (T2 current controlled; T3 superseded/uncontrolled). |
| Requirements | FR-DOC-001–004, FR-ING-004, FR-EVI-001/003 |
| Target maturity | L2. Retrieval method (lexical, vector, hybrid, or LLM-driven navigation) decided by ADR against FR-DOC-001 thresholds, starting from the simplest baseline (D-08). |

### CAP-03 — Process relationship tracing and potential impact
| Field | Content |
|---|---|
| Does | Traverses structured topology upstream/downstream to a bounded depth; separates verified from unverified paths; accounts for recorded redundancy; states **potential topological** impact. |
| Concern type | DET (traversal, redundancy logic), LLM (explaining results in context). |
| Inputs | Structured topology with edge provenance and verification status. |
| Outputs | Traversal outputs (computation evidence, tier inherited from edges). |
| Requirements | FR-PRC-001–003, FR-ING-002, FR-DGM-001 |
| Target maturity | L2. Whether a graph database is needed is decided by ADR. The baseline is traversal over relational/in-memory data, which is likely enough at SRF scale (D-08). |

### CAP-04 — Maintenance history analysis
| Field | Content |
|---|---|
| Does | Retrieves work orders and failure events; computes counts, intervals, recurring modes, and MTBF when the minimum-data rule is met; reports gaps. |
| Concern type | RET (record query), DET (all statistics), LLM (interpreting free text as T3 evidence, summarising patterns with citations). |
| Inputs | Structured maintenance records; free-text fields (T3, untrusted). |
| Outputs | Record evidence (T1 structured fields, T3 free text) and computation evidence. |
| Requirements | FR-MNT-001–004, FR-ING-003 |
| Target maturity | L2. |

### CAP-05 — Deterministic computation
| Field | Content |
|---|---|
| Does | Provides typed, tested, versioned computation tools (date/interval arithmetic, failure statistics, unit conversion, aggregation, graph traversal primitives). |
| Concern type | DET only. |
| Requirements | FR-ARC-001/002, FR-CMP-001–003, NFR-REL-001 |
| Target maturity | L2. Each new computation requires a specification and reference tests before use. |

### CAP-06 — Failure investigation orchestration
| Field | Content |
|---|---|
| Does | Runs the UC-01 workflow: scope → asset context → process context → documents → maintenance history → competing hypotheses (supporting/contradicting/missing evidence) → advisory discriminating checks → verification → classified report. Stops with partial findings when evidence is insufficient. |
| Concern type | LLM (planning, hypothesis generation, evidence relating, drafting), invoking RET/DET tools and VER. |
| Requirements | FR-INT-001–004, FR-INV-001–008 |
| Target maturity | L2 for pumps (P-102 scenarios). Generalisation to other rotating equipment (FR-INV-008) is a later phase. |
| Notes | Detailed workflow and RCA method selection (5-Whys, fault-tree-style decomposition, FMEA-informed failure-mode lists) are specified in 06. |

### CAP-07 — Epistemic classification and evidence management
| Field | Content |
|---|---|
| Does | Maintains the evidence register (IDs, tiers, classifications); assigns and transitions epistemic classes under the rules in 02 §3–4. |
| Concern type | DET (rule enforcement, schema), LLM (proposing class for a drafted statement, which is then rule-checked). |
| Requirements | FR-EPI-001–003, FR-EVI-001–003, FR-INT-003 |
| Target maturity | L2. |

### CAP-08 — Verification
| Field | Content |
|---|---|
| Does | Checks every draft before presentation: citation resolution and support, class rules, number tracing, prohibited content. Revises, downgrades, or removes failing claims. |
| Concern type | VER: deterministic rule checks, plus an independent LLM invocation for semantic support. |
| Requirements | FR-VER-001–003, FR-ARC-002 |
| Target maturity | L2. Its own detection rates are measured with injected-defect tests (11). |

### CAP-09 — State and case-file management
| Field | Content |
|---|---|
| Does | Manages working state, session state, and versioned append-only case files; supports resuming investigations (UC-06); enforces case isolation and retention. |
| Concern type | DET. |
| Requirements | FR-MEM-001–006 |
| Target maturity | L2 for working/session/case files. Cross-case memory is **L0 by design** until FR-MEM-006 is satisfied. |

### CAP-10 — Audit, explanation, and observability
| Field | Content |
|---|---|
| Does | Records complete run traces; supports deterministic replay; explains how a statement was reached; reports cost/latency metrics. |
| Concern type | DET (trace capture, replay), LLM (explanation drafting from the trace). |
| Requirements | FR-AUD-001–003, NFR-OBS-001, NFR-PERF-003 |
| Target maturity | L2. |

### Cross-cutting guard capabilities

| ID | Capability | Requirements |
|---|---|---|
| CAP-G1 | Safety boundary enforcement: no external-write tools, refusal of operating/bypass instructions, hazard handling, safety-critical decision and out-of-competence hand-offs, advisory disclaimers. | FR-SAF-001–006 |
| CAP-G2 | Data classification and outbound data gate (providers, LLM judge, telemetry). | FR-SEC-001/002, NFR-SEC-002/003 |
| CAP-G3 | Untrusted-content handling (indirect prompt-injection defence). | FR-DOC-004, FR-MNT-004, NFR-SEC-001 |
| CAP-G4 | Provider adapter (provider neutrality). | NFR-PRV-001–003 |

---

## 4. Deferred and candidate capabilities

| ID | Capability | Status | Gate before introduction |
|---|---|---|---|
| CAP-D1 | Diagram / P&ID extraction into **unverified** topology | Deferred (D-11, NG-11) | Separate evaluation with user-approved thresholds (FR-DGM-002); human verification workflow (FR-DGM-001). |
| CAP-D2 | Evaluation on public datasets | Deferred (D-05) | Licence and permitted-use review (EVD-006). |
| CAP-D3 | Additional rotating-equipment classes (compressors, fans, turbines…) | Later phase (FR-INV-008, priority L) | FR-INV-008 evaluation on SRF extension. |
| CAP-D4 | Cross-case / long-term memory | Deferred (D-09, NG-10) | Approved retention, provenance, and trust rules; memory-poisoning evaluation (FR-MEM-006). |
| CAP-D5 | Time-series / sensor data analysis | **Not in scope** (NG-08); candidate only | User decision (02 Q-01). If added, it must go through CAP-05 deterministic tools. |
| CAP-D6 | Confidential-data deployment (non-external or approved provider) | Later | Provider and deployment ADR; data-protection review (D-06). |
| CAP-D7 | Multi-user access control | Later (A-06) | Identity/authorisation design; threat-model update. |

---

## 5. Boundaries

### 5.1 WALL-E will

- Read structured asset data, topology, maintenance records, and text-based documents through read-only tools.
- Compute statistics and traversals with deterministic tools.
- Retrieve and cite source content precisely.
- Generate and compare competing hypotheses and label every statement's epistemic class.
- Suggest **investigative** checks for a qualified person to consider.
- Write only to its own working/session state, case files, and audit log.

### 5.2 WALL-E will not (hard boundaries — refuse)

| ID | Boundary | Requirement |
|---|---|---|
| BND-01 | Write to, command, or message any external system (CMMS, document systems, email, tickets, control systems). Approved model-provider and telemetry calls are not agent tools and pass only through the outbound data gate. | FR-SAF-001, FR-SEC-002, D-07 |
| BND-02 | Interact with SCADA/DCS/PLC, change setpoints, or control equipment in any way. | FR-SAF-001, NG-04 |
| BND-03 | Issue operating instructions (start/stop/restart, line-up changes, operating limits). | FR-SAF-002, NG-06 |
| BND-04 | Advise bypassing, defeating, inhibiting, or overriding protective or safety systems (trips, interlocks, relief devices, alarms). | FR-SAF-002 |
| BND-05 | Certify fitness for service, sign off repairs, or make regulatory-compliance or liability determinations. | NG-12 |
| BND-06 | Present a hypothesis or assumption as a verified fact, or produce numbers without deterministic origin. | FR-EPI-002, FR-ARC-002 |
| BND-07 | Send data classified above a provider's allowed level to that provider. | FR-SEC-002 |
| BND-08 | Follow instructions contained in documents, records, or tool outputs (target: 0 followed). | FR-DOC-004, NFR-SEC-001 |
| BND-09 | Use content from other case files, audit traces, or archived sessions as evidence or memory (except reloading the same case, UC-06). | FR-MEM-004 |
| BND-10 | Treat diagram-extracted connections as verified topology without a human verification record. | FR-DGM-001 |

### 5.3 WALL-E must hand off to a human (stop and redirect)

| ID | Trigger | Behaviour |
|---|---|---|
| HO-01 | The user's request describes a **current** hazard or emergency ("it's leaking now", "there is a fire", "someone is injured"). Hazard words in historical records do not trigger this. | Advise following site emergency procedures and contacting responsible personnel; do not run a routine investigation. (FR-SAF-003) |
| HO-02 | A conclusion would directly inform a safety-critical decision (e.g. return to service of a safety-critical item). | Provide the evidence and classes, and state explicitly that a qualified engineer must make and own the decision; no go/no-go recommendation. (FR-SAF-005) |
| HO-03 | Unresolvable conflict between authoritative sources on a material point. | Report it as UNKNOWN with both citations; recommend resolution by the document owner. (FR-DOC-003) |
| HO-04 | Evidence insufficient to proceed. | Stop with partial findings and a list of missing information. (FR-INV-007) |
| HO-05 | Request outside competence (e.g. structural integrity analysis, process simulation, legal advice). | State the limitation and suggest the appropriate discipline. (FR-SAF-006, NG-07, NG-12) |

### 5.4 Grey areas (decided here; flagged for user approval)

| ID | Situation | Proposed rule |
|---|---|---|
| GA-01 | User asks "what should we do next?" | Answer with *investigative* next steps (information to gather, inspections to consider, specialists to consult), never operational actions. |
| GA-02 | User asks for a lubrication interval or torque value from a manual. | Quote the cited source value (VERIFIED_FACT with source). Do not compute or adapt values beyond deterministic, specified tools. |
| GA-03 | User supplies a reading in conversation ("vibration was 12 mm/s"). | Record it as T3 user-report evidence (FR-INT-003). Do not compare it against limits unless the limit is cited and the comparison is performed deterministically. |
| GA-04 | Evidence points strongly to one cause. | It may be a SUPPORTED_CONCLUSION if it meets the rules. The report still lists alternatives considered and why they were set aside. |

---

## 6. Supporting components (function only — technology undecided)

Each component exists only because a capability needs it (D-01). Technology is selected in 04 via ADRs, starting from the simplest baseline (D-08, NFR-ARCH-001).

| ID | Component (function) | Serves | Simplest baseline to evaluate first | Candidates to compare in 04 |
|---|---|---|---|---|
| SC-01 | Asset & maintenance record store | CAP-01, CAP-04 | Embedded relational database or validated flat files loaded in memory | Relational DB server; document store |
| SC-02 | Topology model & traversal | CAP-03 | Adjacency tables + deterministic traversal code | Recursive SQL queries; graph library; dedicated graph DB |
| SC-03 | Document store & retrieval | CAP-02 | Lexical search (e.g. BM25) over sectioned text with metadata filters | Vector search; hybrid lexical+vector; reranking; LLM-guided navigation of document structure |
| SC-04 | Computation tool library | CAP-05 | Plain, typed functions with unit tests | — |
| SC-05 | Agent orchestration loop | CAP-06 | Hand-written tool-use loop over a provider adapter | Claude Agent SDK; other agent frameworks; MCP for tool exposure |
| SC-06 | Provider adapter & policy gate | CAP-G2, CAP-G4 | Thin interface + mock provider + Anthropic adapter | Multi-provider abstraction libraries |
| SC-07 | Case-file & state store | CAP-09 | Versioned structured files (e.g. JSON) with append-only history | Embedded DB |
| SC-08 | Audit trace store | CAP-10 | Append-only structured log files | Tracing/observability tooling |
| SC-09 | Verification engine | CAP-08 | Deterministic rule checks + separate LLM support-check call | Specialised entailment/citation-check models |
| SC-10 | Minimal interface | NFR-USE-001 | CLI + machine-readable output for evaluation | Simple HTTP API; minimal web view |
| SC-11 | Evaluation harness | All (11) | Scripted runs over the SRF with metric computation | Evaluation frameworks |

> **Engineering explanation.** The "simplest baseline" column is not a decision. It is the *control group*. At SRF scale (one process unit, tens of assets, dozens of documents), a dedicated graph database or vector index may add operational complexity without improving any metric. NFR-ARCH-001 requires 04 to show why the baseline fails a requirement before choosing something heavier. The same logic applies to agent frameworks and MCP: they can bring useful structure, but they also bring dependencies and abstractions. They have to earn their place against a hand-written loop.

---

## 7. Traceability matrix

### 7.1 Use case → capabilities

| Use case | Capabilities |
|---|---|
| UC-01 Investigate failure | CAP-06 (orchestrates CAP-01–05, 07–10), CAP-G1–G4 |
| UC-02 Understand asset | CAP-01, CAP-07, CAP-08, CAP-10 |
| UC-03 Process relationships & impact | CAP-03, CAP-05, CAP-07, CAP-08 |
| UC-04 Maintenance history | CAP-04, CAP-05, CAP-07, CAP-08 |
| UC-05 Documentation | CAP-02, CAP-07, CAP-08 |
| UC-06 Resume case | CAP-09, CAP-07, CAP-06 |

### 7.2 Decision → requirements → capabilities

| Decision | Key requirements | Capabilities |
|---|---|---|
| D-01 Agent is the product | NFR-ARCH-001, NG-01/09 | All; SC-* scoped by capability |
| D-02 Users | FR-SAF-004, A-01 | CAP-06 |
| D-03 First use case (P-102) | FR-INV-001–008, EVD-001/002 | CAP-06 |
| D-04 ISO 14224 as reference | FR-AST-002, FR-INV-008 | CAP-01, CAP-06 |
| D-05 Synthetic data first | EVD-001–006 | SC-11, CAP-D2 |
| D-06 Provider-neutral, no confidential data externally | FR-SEC-001/002, NFR-PRV-001–003, NFR-SEC-003 | CAP-G2, CAP-G4 |
| D-07 Read-only advisory | FR-SAF-001–006, FR-INV-005, FR-ING-005 | CAP-G1 (boundaries BND-01–05) |
| D-08 No premature infrastructure | NFR-ARCH-001/002 | SC-01–11 |
| D-09 Minimal memory | FR-MEM-001–006 | CAP-09, CAP-D4 |
| D-10 Separation of concerns | FR-ARC-001/002, FR-CMP-*, FR-VER-* | CAP-05, CAP-08 |
| D-11 Text first, diagrams later | FR-DGM-001/002, FR-PRC-002, A-05 | CAP-03, CAP-D1 |
| D-12 Epistemic classes | FR-EPI-*, FR-INV-003/006, NFR-QUAL-003 | CAP-07 |
| D-13 Educational workflow | PC-01, FR-AUD-003 | (process) |

### 7.3 Requirement → capability (coverage)

Every requirement in 02 maps to at least one owning capability or to a project-level owner.

| Requirements | Owning capability / owner |
|---|---|
| FR-ARC-001/002 | CAP-05, CAP-08 |
| FR-INT-001, FR-INT-004 | CAP-06 |
| FR-INT-002 | CAP-01 |
| FR-INT-003 | CAP-07 |
| FR-AST-001–003 | CAP-01 |
| FR-PRC-001–003 | CAP-03 |
| FR-DOC-001–003 | CAP-02 |
| FR-DOC-004, FR-MNT-004 | CAP-G3 (with CAP-02 / CAP-04) |
| FR-MNT-001–003 | CAP-04 (statistics in CAP-05) |
| FR-CMP-001–003 | CAP-05 |
| FR-INV-001–008 | CAP-06 |
| FR-EPI-001–003, FR-EVI-001–003 | CAP-07 |
| FR-VER-001–003 | CAP-08 |
| FR-MEM-001–006 | CAP-09 |
| FR-AUD-001–003 | CAP-10 |
| FR-SAF-001–006 | CAP-G1 |
| FR-SEC-001/002 | CAP-G2 |
| FR-ING-001–005 | SC-01, SC-02, SC-03 (serving CAP-01–04) |
| FR-DGM-001 | CAP-03 (edge state model) |
| FR-DGM-002 | CAP-D1 (gate) |
| NFR-QUAL-001/002/006 | CAP-02, CAP-07, CAP-08 |
| NFR-QUAL-003/007 | CAP-07, CAP-08 |
| NFR-QUAL-004/005 | CAP-06 |
| NFR-PERF-001–003 | CAP-10 (measurement); SC-11 |
| NFR-REL-001 | CAP-05 |
| NFR-REL-002 | SC-11 (evaluation harness) |
| NFR-REL-003 | CAP-06, CAP-10 |
| NFR-PRV-001–003 | CAP-G4 |
| NFR-SEC-001 | CAP-G3 |
| NFR-SEC-002/003 | CAP-G2 |
| NFR-ARCH-001/002 | Project-level (ADR process, 04) |
| NFR-OBS-001 | CAP-10 |
| NFR-USE-001/002 | SC-10 |
| EVD-001–006 | SC-11 |

### 7.4 Requirement → verification (summary)

Every FR/NFR in 02 carries a Verify method (T/E/I/R). Evaluation-dependent requirements (method E) map to SRF scenario IDs that will be defined in 11. Until then the "planned evaluation" link is the requirement ID itself. Doc 11 will add a column mapping each E-verified requirement to scenario and metric IDs, and a coverage check that no E-verified requirement is left unmapped.

---

## 8. Assumptions introduced in this document (require user approval)

| ID | Assumption |
|---|---|
| A-14 | Maturity levels L0–L3 are an adequate way to express the roadmap in 12. |
| A-15 | The grey-area rules GA-01–GA-04 reflect acceptable advisory behaviour for professional users. |
| A-16 | The simplest baselines listed in §6 are the starting point for each ADR in 04, unless a requirement clearly rules one out up front. |
