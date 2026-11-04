# 01 — WALL-E Agent Charter

| Field | Value |
|---|---|
| Status | **DRAFT — awaiting user review** |
| Phase | 0 — Product Definition & Architecture |
| Depends on | User decisions recorded in §2 |
| Feeds | 02-requirements, 03-capabilities-boundaries, all later documents |


> **Status note (Phase 1).** This document is v0.1 and was written for a maintenance-investigation direction. For Phase 1, `docs/spec/phase-1-document-intelligence.md` governs wherever the two conflict. Maintenance-specific items (D-02, D-03, UC-01–UC-06, FR-AST-\*, FR-PRC-\*, FR-MNT-\*, FR-INV-\*, EVD-001/002, A-02) are inactive pending the v0.2 rewrite. Cross-cutting requirements remain in force as listed in the Phase 1 specification §17.

---

## 1. Purpose of this document

This charter defines **what WALL-E is, who it serves, what it is for, and what it is explicitly not**. Every requirement in `02-requirements.md` and every capability in `03-capabilities-boundaries.md` must trace back to a goal, use case, or decision in this document. If a later proposal cannot be traced here, it is out of scope until the charter is amended and approved.

---

## 2. Decision register (user-approved inputs)

These decisions were made by the project owner and are binding for the Phase 0 specification. They are referenced throughout as `D-xx`.

| ID | Decision |
|---|---|
| D-01 | **WALL-E is the product.** Databases, document processing, retrieval, graph reasoning, APIs, and interfaces are *supporting components* that exist only to serve WALL-E. No independent platform goals. |
| D-02 | **Primary users:** Reliability Engineers and Maintenance Engineers. |
| D-03 | **First use case:** investigating the failure of rotating equipment, starting with a pump (reference tag **P-102**), covering downstream impact, relevant documentation, maintenance history, supporting evidence, and competing hypotheses. |
| D-04 | **Industry scope:** generic process industry. ISO 14224 is used as a *domain reference* (vocabulary, taxonomy), not as a restriction to oil & gas. |
| D-05 | **Evaluation data:** a **synthetic reference facility** first. Public datasets later, only after licence and permitted-use review. No real industrial documents are approved for this project. |
| D-06 | **LLM deployment:** Anthropic API initially, with synthetic data only. Architecture must be **provider-neutral**. It must **not** be assumed that confidential customer data may be sent to an external API. |
| D-07 | **Autonomy:** **read-only and advisory** across all phases of this specification. No external writes, no equipment control, no SCADA/DCS interaction, no execution of operational actions. |
| D-08 | **No premature infrastructure commitment.** Claude Agent SDK, MCP, graph databases, vector search, and other infrastructure are *candidates* to be researched and compared against requirements. The **simplest architecture that satisfies the evaluation criteria** wins. |
| D-09 | **Minimal memory:** working state; session state when needed; investigation case files. Retention, provenance, and trust rules must be defined **before** any persistent memory is introduced. |
| D-10 | **Separation of concerns:** deterministic computation, document retrieval, LLM reasoning, and verification are explicitly separate. The LLM must not replace deterministic calculation or present unsupported hypotheses as facts. |
| D-11 | **Input scope:** structured asset data and text-based documents first. P&ID / diagram extraction is a **later, separately evaluated** capability; unverified diagram extraction must never silently become verified process topology. |
| D-12 | **Epistemic discipline:** every investigation distinguishes **verified facts, evidence-supported conclusions, hypotheses, assumptions, and unknown/missing information**. |
| D-13 | **Educational workflow:** architectural decisions, alternatives, trade-offs, and implementation concepts are explained so the project owner understands the engineering, not just the output. |

---

## 3. Vision

> **WALL-E is an evidence-grounded industrial AI agent that helps reliability and maintenance engineers understand equipment, its process context, and its history — and investigate failures by assembling cited evidence, reasoning over competing hypotheses, and stating clearly what is known, what is inferred, what is assumed, and what is still missing.**

WALL-E is valuable because a failure investigation today requires an engineer to manually gather information scattered across asset registers, maintenance records, OEM manuals, procedures, previous investigation reports, and process drawings — and then to hold competing explanations in mind without losing track of which claims are actually supported. WALL-E automates the *gathering, organising, computing, and cross-checking*, while the engineer retains *judgement and decision authority*.

### 3.1 Design principles

| ID | Principle | Why it matters |
|---|---|---|
| P-1 | **Evidence before eloquence.** A shorter answer with complete citations beats a fluent answer with gaps. | Engineers act on investigation outputs; an uncited claim is a liability. |
| P-2 | **Say what kind of claim it is.** Every statement carries an epistemic class (D-12). | Prevents a hypothesis from being read as a finding. |
| P-3 | **Compute, don't guess.** Numbers come from deterministic tools, never from the model's text generation (D-10). | LLMs are unreliable at arithmetic and date logic; deterministic code is testable. |
| P-4 | **Advise, never act.** WALL-E has no capability to change anything outside its own case files and logs (D-07). | Removes an entire class of safety and security risk by construction. |
| P-5 | **Simplest thing that passes evaluation.** Infrastructure is added only when an evaluation shows it is needed (D-08). | Avoids building a platform instead of an agent (D-01). |
| P-6 | **Untrusted by default.** Document text and free-text records are data, not instructions. | Industrial documents and work-order notes are an indirect prompt-injection surface. |
| P-7 | **Provider-neutral core.** The agent's logic does not depend on one LLM vendor (D-06). | Future confidential deployments may require a different provider or a local model. |

---

## 4. Target users

### 4.1 Primary users (D-02)

| ID | User | Typical goals with WALL-E | Expertise assumption |
|---|---|---|---|
| U-1 | **Reliability Engineer** | Run failure investigations / RCA, identify recurring failure modes, assess bad actors, review failure history and intervals. | Understands failure modes, RCA methods, and basic reliability statistics. |
| U-2 | **Maintenance Engineer** | Understand an asset's history and documentation quickly, prepare for repair or inspection, check what was done previously, find the relevant manual sections and procedures. | Understands equipment, work orders, and maintenance procedures. |

Both are **qualified professionals** who remain accountable for conclusions. WALL-E's outputs are inputs to their judgement, not substitutes for it.

### 4.2 Secondary consumers (read-only, later)

| ID | Consumer | Relationship |
|---|---|---|
| U-3 | Process Engineer | May read investigation reports for process-impact context. Not a design target in Phase 1. |
| U-4 | Maintenance / Reliability Supervisor | May review case files prepared by U-1/U-2. Not a design target in Phase 1. |

### 4.3 Explicitly not users

- Control-room operators making **real-time operational decisions**.
- Anyone seeking WALL-E to **authorise, execute, or sign off** an operational or safety action.

---

## 5. Use cases

UC-01 is the anchor use case (D-03). UC-02 to UC-05 are both standalone queries **and** sub-steps of UC-01. UC-06 supports multi-session investigations.

### UC-01 — Investigate a rotating-equipment failure (primary)

| Field | Content |
|---|---|
| Actor | U-1 (primary), U-2 |
| Trigger | Engineer reports or is assigned a failure/abnormal condition on a rotating-equipment item, e.g. *"P-102 tripped on high vibration on 14 March; investigate."* |
| Preconditions | The asset exists in the structured asset data; relevant documents and maintenance records are available to WALL-E's read-only tools. |
| Main flow | 1. Resolve the asset (tag → asset record); confirm scope and time window with the user if ambiguous. 2. Assemble asset context (type, hierarchy, specification, criticality if available). 3. Trace process relationships: upstream sources, downstream consumers, redundancy (e.g. standby unit), and **potential** downstream impact. 4. Retrieve relevant documentation (datasheets, OEM manual sections, procedures, previous investigations, inspection reports) with passage-level citations. 5. Retrieve maintenance history; compute failure statistics deterministically; identify recurring failure modes. 6. Generate **competing hypotheses**; for each, list supporting evidence, contradicting evidence, and missing evidence. 7. Propose **discriminating checks** (advisory only) that would distinguish between hypotheses. 8. Verify the draft (citations, classifications, computations). 9. Produce an investigation report and case file in which every statement carries an epistemic class. |
| Postconditions | A versioned case file exists; nothing outside WALL-E has been modified. |
| Alternate flows | A1: asset not found / ambiguous → ask for clarification; never invent an asset. A2: evidence insufficient → report UNKNOWN items and stop with partial findings rather than speculating. A3: active-hazard language detected → advise following site emergency procedures; do not continue as a routine investigation (see 03 §5). |
| Out of scope | Executing checks, issuing work orders, changing equipment state, live sensor/DCS access. |

### UC-02 — Understand an asset

*"What is P-102, what does it serve, and what is its specification?"* — Returns asset record, position in hierarchy, key specification attributes, related documents, all cited.

### UC-03 — Trace process relationships and potential impact

*"If P-102 fails, what is downstream and is there redundancy?"* — Returns upstream/downstream relationships from structured topology, each with provenance and verification status, and a list of **potentially** affected items. Impact is topological, not a process simulation.

### UC-04 — Analyse maintenance history

*"Summarise P-102's failure history over the last five years."* — Returns work orders and failure events, deterministically computed statistics (counts, intervals, recurring modes), and an explicit statement of data sufficiency.

### UC-05 — Find and explain documentation

*"What does the OEM manual say about the bearing lubrication interval for P-102?"* — Returns relevant passages with document ID, revision, and location; flags conflicting or superseded documents.

### UC-06 — Resume and review an investigation case

*"Continue the P-102 investigation; a new inspection report has been added."* — Loads the case file, records the new evidence, re-evaluates affected hypotheses, and logs what changed and why.

---

## 6. Goals and success definition

| ID | Goal | Measured by (provisional; finalised in 11-evaluation-acceptance) |
|---|---|---|
| G-1 | Investigations are **evidence-grounded**. | Citation precision and recall on the synthetic reference facility (SRF) evaluation set. See NFR-QUAL-001/002. |
| G-2 | Investigations are **epistemically honest**. | Classification accuracy against labelled ground truth; zero hypotheses presented as verified facts. See FR-EPI-*, NFR-QUAL-003. |
| G-3 | Investigations are **useful**. | Planted root cause appears among WALL-E's hypotheses; key evidence retrieved; expert rubric score. See NFR-QUAL-004/005. |
| G-4 | WALL-E is **safe by construction**. | Zero external-write capabilities; zero unauthorised actions under adversarial evaluation. See FR-SAF-*, NFR-SEC-*. |
| G-5 | WALL-E is **reproducible and auditable**. | 100% of runs have complete traces; deterministic outputs replay identically. See FR-AUD-*, NFR-REL-*. |
| G-6 | WALL-E is **lean**. | Every infrastructure component is justified by a requirement and an evaluation result (ADR). See NFR-ARCH-001. |
| G-7 | The owner **understands the engineering**. | Each ADR includes alternatives, trade-offs, and an explanation section (D-13). See PC-01. |

---

## 7. Non-goals

| ID | Non-goal | Rationale |
|---|---|---|
| NG-01 | Building an industrial software platform, data platform, or suite of products. | D-01. |
| NG-02 | Replacing CMMS, historian, EAM, or document management systems. WALL-E **reads** representative data; it is not a system of record. | D-01, D-07. |
| NG-03 | Any write to external systems (work orders, CMMS, document systems, email, tickets). | D-07. |
| NG-04 | Equipment control, SCADA/DCS interaction, setpoint changes, or execution of operational actions. | D-07. |
| NG-05 | Acting as, or being part of, a safety instrumented function or any safety-rated system. | Safety; D-07. |
| NG-06 | Issuing operating instructions (e.g. "restart the pump", "bypass the trip"). WALL-E may suggest *investigative* checks for a qualified person to consider. | D-07; see 03 §5. |
| NG-07 | Dynamic process simulation, hydraulic modelling, or rigorous engineering calculations beyond validated deterministic tools explicitly specified later. | Scope control; D-10. |
| NG-08 | Real-time monitoring, alarming, or live time-series ingestion (not requested in this specification; may be proposed later as a separate capability). | Scope control. |
| NG-09 | Dashboards, reporting suites, or a general-purpose UI. A minimal interface sufficient to use and evaluate the agent is in scope. | D-01. |
| NG-10 | Persistent cross-case long-term memory before retention, provenance, and trust rules are approved. | D-09. |
| NG-11 | Diagram/P&ID extraction in the first capability phase. | D-11. |
| NG-12 | Regulatory compliance determinations, fitness-for-service sign-off, or legal/incident liability conclusions. | Accountability remains with qualified humans. |

---

## 8. Constraints

| ID | Constraint | Source |
|---|---|---|
| C-01 | Only **synthetic** data (and, later, licence-cleared public data) may be processed. | D-05 |
| C-02 | Only data classified as permitted may be sent to an external LLM API; default deny. | D-06 |
| C-03 | The core agent must run against at least one non-Anthropic model adapter or a mock provider without code changes to core logic. | D-06 |
| C-04 | No tool may perform writes outside WALL-E's own state stores (case files, audit log, working/session state). | D-07 |
| C-05 | Infrastructure technology choices require an ADR comparing alternatives against requirements and evaluation evidence. | D-08 |
| C-06 | The project follows the approval gates in `CLAUDE.md`. | Project policy |

### 8.1 Project-process constraint

| ID | Constraint |
|---|---|
| PC-01 | Every architectural decision (ADR) must include: context, options considered, trade-offs, decision, consequences, and a plain-language **"Engineering explanation"** section (D-13). |

---

## 9. Assumptions (require user approval)

| ID | Assumption | Impact if wrong |
|---|---|---|
| A-01 | Users are qualified engineers who review outputs before acting. WALL-E's tone and boundaries are designed for professionals, not the public. | Boundary and wording rules in 03 would need strengthening. |
| A-02 | The SRF models **one process unit** containing a duty/standby pump pair. **P-102** is an *equipment-set record* (functional grouping) with child equipment units **P-102A** and **P-102B**, plus upstream/downstream equipment, sufficient to exercise all UC-01 steps. "P-102" therefore resolves to the set; unit-specific events are attributed to A or B (FR-INT-002). | SRF design (in 11) changes; P-102 naming in examples changes. |
| A-03 | "Downstream impact" means **topological** impact (what is connected and may be affected, accounting for redundancy recorded in structured data), not quantitative process consequence. | Would require a simulation capability, currently NG-07. |
| A-04 | Maintenance history is available as **structured records** (work orders, failure events) with optional free-text fields; free text is treated as untrusted data. | Ingestion and parsing scope grows. |
| A-05 | Text-based documents means: PDFs with an extractable text layer, plain text, and Markdown. Scanned/image-only PDFs and drawings are out of the first capability phase. | OCR would enter scope earlier. |
| A-06 | Single user per session; no multi-tenant or role-based access control in the first capability phase, but the design must not preclude it. | Identity/authorisation enters scope earlier. |
| A-07 | Response-time targets are interactive-but-not-real-time (minutes for a full investigation). | NFR-PERF targets change. |
| A-08 | ISO 14224 is referenced for vocabulary and structure only; WALL-E specifications will not reproduce copyrighted tables from the standard. Taxonomy terms used in this specification should be checked against the standard text before being relied on. | Licensing or terminology rework. |
| A-09 | Language and runtime (e.g. Python) are **not** fixed in this document; they are decided by ADR in 04. | — |

---

## 10. Glossary (charter-level)

| Term | Meaning in this project |
|---|---|
| Asset | A physical item in the facility hierarchy (e.g. a pump), identified by a tag. |
| Tag | The facility identifier of an asset, e.g. `P-102A`. |
| Case file | The structured, versioned record of one investigation (D-09). |
| Epistemic class | One of: VERIFIED_FACT, SUPPORTED_CONCLUSION, HYPOTHESIS, ASSUMPTION, UNKNOWN (defined in 02 §3). |
| Evidence item | A cited unit of source content (a record, a document passage, or a deterministic computation output) used to support or contradict a claim. |
| SRF | Synthetic Reference Facility — the evaluation dataset (D-05). |
| Supporting component | Infrastructure that exists only to serve a WALL-E capability (D-01). |
| Topology | The structured model of process connections between assets. |
