# 02 — WALL-E Requirements

| Field | Value |
|---|---|
| Status | **DRAFT — awaiting user review** |
| Phase | 0 — Product Definition & Architecture |
| Depends on | 01-agent-charter (decisions D-xx, use cases UC-xx, goals G-x, assumptions A-xx) |
| Feeds | 03, 04–12 |


> **Status note (Phase 1).** This document is v0.1 and was written for a maintenance-investigation direction. For Phase 1, `docs/spec/phase-1-document-intelligence.md` governs wherever the two conflict. Maintenance-specific items (D-02, D-03, UC-01–UC-06, FR-AST-\*, FR-PRC-\*, FR-MNT-\*, FR-INV-\*, EVD-001/002, A-02) are inactive pending the v0.2 rewrite. Cross-cutting requirements remain in force as listed in the Phase 1 specification §17.

---

## 1. How to read this document

### 1.1 Requirement format

Every requirement has:

- **ID** — `FR-<area>-nnn` (functional) or `NFR-<area>-nnn` (non-functional).
- **Priority** — **M** (must, Phase 1 capability), **S** (should, Phase 1 if feasible), **L** (later phase; captured now so the design does not preclude it).
- **Statement** — "WALL-E shall…" (normative).
- **AC** — acceptance criteria; measurable and checkable.
- **Verify** — method: **T** automated test, **E** evaluation on the SRF, **I** inspection/static check, **R** expert review.
- **Trace** — to decisions (D-xx), use cases (UC-xx), and goals (G-x) in 01. Capability traces (CAP-xx) are in 03 §7.3.

### 1.2 Provisional thresholds

Numerical thresholds marked **(prov.)** are provisional. They will be confirmed or adjusted in `11-evaluation-acceptance.md` once the SRF evaluation set is designed and a baseline is measured. Changing a provisional threshold requires user approval.

### 1.3 Requirement areas

| Area | Scope |
|---|---|
| ARC | Separation of concerns (§2) |
| INT | Investigation intake and scoping |
| AST | Asset identification and context |
| PRC | Process relationships and potential impact |
| DOC | Document retrieval and comprehension |
| MNT | Maintenance history |
| CMP | Deterministic computation |
| INV | Investigation reasoning and reporting |
| EPI | Epistemic classification |
| EVI | Evidence and citation |
| VER | Verification |
| MEM | Memory and state |
| AUD | Audit and traceability |
| SAF | Safety and autonomy boundaries |
| SEC | Security and data protection |
| ING | Supporting-component input requirements (ingestion) |
| DGM | Diagram extraction (later; guard requirements now) |
| EVD | Evaluation data |
| QUAL, PERF, REL, PRV, ARCH, OBS, USE | Non-functional areas |

---

## 2. Separation of concerns (D-10)

This is the central architectural requirement and is stated first because many other requirements depend on it. WALL-E is composed of **four distinct kinds of work**, which must remain separately implemented, separately testable, and separately visible in the audit trace.

| Concern | Responsible for | Must NOT do |
|---|---|---|
| **Deterministic computation** | Counting, date/interval arithmetic, statistics (e.g. MTBF), unit conversion, graph traversal, filtering, sorting, schema validation. | Use an LLM to produce its outputs. |
| **Retrieval** | Finding and returning source content (records, document passages) with stable identifiers and locations. | Paraphrase, summarise, or infer; it returns source content as-is. |
| **LLM reasoning** | Interpreting the question, planning tool use, relating evidence to hypotheses, drafting explanations and reports. | Generate numbers that should be computed; assert facts without citations; upgrade a claim's epistemic class without evidence. |
| **Verification** | Independently checking the draft: citations support claims, classes obey rules (§3), numbers match computation outputs, constraints are respected. | Be skipped, or be performed solely by the same generation step it checks. |

> **Engineering explanation.** An LLM is excellent at language and at relating pieces of evidence, but it produces plausible text, not guaranteed-correct text. By forcing numbers through code, facts through retrieval, and the final draft through a separate checker, each failure mode becomes *detectable* rather than hidden inside fluent prose. It also makes each part testable on its own: you can unit-test an MTBF function; you cannot unit-test "the model was probably right."

| ID | Pri | Requirement |
|---|---|---|
| FR-ARC-001 | M | WALL-E shall implement deterministic computation, retrieval, LLM reasoning, and verification as separately invocable units with defined inputs and outputs. **AC:** each unit has its own test suite runnable without the others (using fixtures/mocks); the audit trace labels every step with its concern type. **Verify:** T, I. **Trace:** D-10, G-5. |
| FR-ARC-002 | M | Any numerical value, date difference, count, or aggregate appearing in a WALL-E output shall originate from, and reference, one of: a structured record field, a cited document span, a deterministic computation output, or a user-report evidence item (FR-INT-003). Identifiers that contain digits (tags, record IDs, revisions) are excluded from this check. **AC:** on the SRF evaluation set, 100% of numerical values in reports are traceable to one of these origins; an automated check flags any untraceable number. **Verify:** T, E. **Trace:** D-10, P-3, G-1. |

---

## 3. Epistemic classes (D-12)

**Unit of classification.** A *claim* is the atomic unit: one assertion stored as a schema object (`claim_id`, text, class, evidence links, reasoning link, status). Reports are rendered from claims. Prose that is not a claim is limited to headings, the scope statement, and the advisory notice. "100% classified" therefore means every claim object has a class, and no free assertion exists outside a claim object (checked by schema).

Every claim in an investigation output must carry exactly one of the following classes.

| Class | Definition | Minimum evidence rule |
|---|---|---|
| **VERIFIED_FACT** | A statement that directly reproduces or restates content from an **authoritative source** (§4, tier T1/T2), with no unresolved conflict among authoritative sources. | ≥1 citation to a T1/T2 source whose cited span/record directly states it. Note: "verified" means *verified against the source*, not "true in the world." |
| **SUPPORTED_CONCLUSION** | A statement inferred from cited evidence via stated reasoning and/or deterministic computation. | ≥1 citation to evidence **and** an explicit reasoning link (or computation reference). Must not rest solely on T4 sources. |
| **HYPOTHESIS** | A candidate explanation that is plausible but not sufficiently established. | Must list supporting evidence, contradicting evidence, and missing evidence (any may be empty, but must be stated as empty). Carries a **status**: `open`, `supported` (promoted; see §3.1), or `set_aside` (with the reason and the contradicting evidence). Set-aside hypotheses remain in the report. |
| **ASSUMPTION** | A statement taken as true for the purpose of reasoning without supporting evidence. | Must state who/what introduced it (user, WALL-E default, or SRF configuration) and what conclusions depend on it. |
| **UNKNOWN** | Information that is needed for the investigation but is missing, unavailable, or unresolved (including unresolved conflicts). | Must state what is missing and, where possible, how it could be obtained. |

### 3.1 Class transition rules

| From → To | Allowed when |
|---|---|
| HYPOTHESIS → SUPPORTED_CONCLUSION | New evidence meets the SUPPORTED_CONCLUSION rule **and** contradicting evidence has been addressed in the reasoning. Transition is logged with the evidence that triggered it. |
| Any → VERIFIED_FACT | Only if the statement meets the VERIFIED_FACT rule directly. Reasoning alone never produces a VERIFIED_FACT. |
| ASSUMPTION → any other class | Only by attaching evidence that meets the target class's rule. |
| VERIFIED_FACT → UNKNOWN | When a conflicting authoritative source is found and the conflict is unresolved. |
| Any downgrade | Always allowed; must be logged with reason. Strength order, from strongest to weakest: VERIFIED_FACT > SUPPORTED_CONCLUSION > HYPOTHESIS. ASSUMPTION and UNKNOWN are not on this scale: any claim may move to UNKNOWN (unresolved), and a claim kept without evidence must become an ASSUMPTION with its owner stated. |

> **Engineering explanation.** In RCA, the most damaging error is *premature convergence*: a hypothesis gets repeated until it sounds like a fact. Making the class an explicit, rule-checked field (instead of relying on hedging words like "likely") turns that error into something the verifier can catch.

---

## 4. Source trust tiers

Evidence quality depends on where it comes from. Each evidence item carries a tier.

| Tier | Source type | Examples | May support VERIFIED_FACT? |
|---|---|---|---|
| T1 | Structured authoritative records | Asset register entries; structured work-order fields (dates, codes, asset ID); structured topology edges marked verified. | Yes (inference-bearing fields: attributed form only, see below) |
| T2 | Controlled documents (current revision) | Datasheets, OEM manuals, approved procedures, approved previous investigation reports. | Yes (conclusions of previous investigations: attributed form only, see below) |
| T3 | Uncontrolled or lower-assurance records | Free-text work-order notes, inspection remarks, superseded document revisions, user-reported observations. | No — may support SUPPORTED_CONCLUSION or HYPOTHESIS, labelled as T3. |
| T4 | Unverified machine-derived content | Diagram/P&ID extraction not yet human-verified (D-11); any LLM-generated summary. | No — and a SUPPORTED_CONCLUSION may not rest solely on T4. |

Deterministic computation outputs inherit the **least-trusted (highest-numbered)** tier among their inputs.

**Inference-bearing fields (proposed rule; requires approval).** Some T1/T2 content is itself an earlier *inference*: coded failure cause and failure mechanism fields in work orders, and root-cause conclusions in previous investigation reports. Such content:
- may support a VERIFIED_FACT only in *attributed* form: "WO-1234 records failure cause code *wear*" or "RCA-2023-07 concluded bearing fatigue";
- is capped at SUPPORTED_CONCLUSION (and normally HYPOTHESIS support) when used as a claim about the **current** event or about what actually happened.

Cause codes in maintenance systems are often entered quickly and inconsistently, and a previous RCA conclusion is itself a judgement. Treating them as facts about the world would launder old inferences into new "facts".

> **Engineering explanation.** Tiers make the *trustworthiness of a source* explicit instead of implicit. A technician's free-text note ("bearing sounded rough") is valuable evidence but is not the same as a measured vibration record. Tier inheritance prevents a calculation from "laundering" weak inputs into a strong-looking number.

---

## 5. Functional requirements

### 5.1 Intake and scoping (INT)

| ID | Pri | Requirement |
|---|---|---|
| FR-INT-001 | M | WALL-E shall accept an investigation request that identifies an asset by tag or description, plus an optional problem statement and time window. **AC:** requests with tag only, tag + symptom, and tag + symptom + window are all accepted on SRF test cases. **Verify:** T. **Trace:** UC-01. |
| FR-INT-002 | M | WALL-E shall resolve the asset reference to exactly one asset record, or ask a clarifying question when zero or multiple candidates match. It shall never proceed with an invented asset. **AC:** on SRF resolution tests, 100% correct outcomes and 0% fabricated assets: (a) "P-102" resolves to the P-102 equipment-set record (A-02); if the request concerns a unit-specific event and the unit (A/B) cannot be determined from the request or records, WALL-E asks which unit; (b) a non-existent tag returns explicit not-found; (c) a description matching several assets triggers clarification. **Verify:** T, E. **Trace:** UC-01 A1, G-2. |
| FR-INT-003 | M | User-supplied observations (symptoms, dates, readings) shall be recorded as evidence items of tier T3 with source "user report", not as VERIFIED_FACTs. **AC:** in SRF tests, 100% of user-supplied observations appear as T3 evidence; none is classified VERIFIED_FACT unless corroborated by a T1/T2 source. **Verify:** T. **Trace:** D-12, §4. |
| FR-INT-004 | S | WALL-E shall restate the investigation scope (asset, symptom, window, assumptions) before running a full investigation, and record it in the case file. **AC:** every case file contains a scope section; scope changes are versioned. **Verify:** T. **Trace:** UC-01, D-12. |

### 5.2 Asset context (AST)

| ID | Pri | Requirement |
|---|---|---|
| FR-AST-001 | M | WALL-E shall retrieve the asset record (tag, type/class, description, location in hierarchy, key specification attributes, criticality if present) with record-level citations. **AC:** for all SRF assets, retrieved attributes match the source record exactly (100%). **Verify:** T. **Trace:** UC-02, UC-01. |
| FR-AST-002 | M | WALL-E shall represent the asset hierarchy using levels informed by ISO 14224 (e.g. plant/unit → system → equipment unit → subunit → maintainable item), without requiring every level to be populated. **AC:** SRF hierarchy queries return parent/child chains matching ground truth; missing levels are reported as absent, not inferred. **Verify:** T. **Trace:** D-04, A-08. |
| FR-AST-003 | M | WALL-E shall identify redundancy relationships recorded in structured data (e.g. duty/standby P-102A/B). **AC:** SRF redundancy queries match ground truth 100%; where redundancy is not recorded, WALL-E reports UNKNOWN rather than assuming. **Verify:** T, E. **Trace:** UC-03, A-02. |

### 5.3 Process relationships and potential impact (PRC)

| ID | Pri | Requirement |
|---|---|---|
| FR-PRC-001 | M | WALL-E shall trace upstream and downstream process relationships of an asset from structured topology data to a configurable depth. **AC:** on SRF topology tests, returned upstream/downstream sets match ground truth (precision and recall = 100%). **Verify:** T. **Trace:** UC-03, D-10. |
| FR-PRC-002 | M | Every topology edge shall carry provenance (source record/document) and a verification status (`verified` / `unverified`). Traversal results shall separate paths using only verified edges from paths containing any unverified edge. **AC:** SRF tests with mixed edges show unverified paths never appear in the "verified" result set. **Verify:** T. **Trace:** D-11, §4. |
| FR-PRC-003 | M | WALL-E shall report **potential** downstream impact as a topological statement (what is connected and could be affected, accounting for recorded redundancy), labelled as SUPPORTED_CONCLUSION or HYPOTHESIS as appropriate — never as a quantitative consequence. **AC:** 100% of impact statements in SRF reports carry a class and cite the traversal output; no impact statement claims magnitude/duration unless sourced. **Verify:** T, R. **Trace:** UC-01, A-03, NG-07. |

### 5.4 Documents (DOC)

| ID | Pri | Requirement |
|---|---|---|
| FR-DOC-001 | M | WALL-E shall retrieve passages relevant to a query from text-based documents (A-05) and return them with document ID, title, revision, and location (page/section). **AC:** on the SRF retrieval set, recall@k of gold passages ≥ 0.85 and precision@k ≥ 0.70 (prov.; k fixed in 11). **Verify:** E. **Trace:** UC-05, UC-01, G-1. |
| FR-DOC-002 | M | WALL-E shall prefer the current revision of a controlled document and identify superseded revisions as T3. **AC:** on SRF revision tests, 100% of citations to superseded revisions are labelled as such; current revision is preferred when both are relevant. **Verify:** T, E. **Trace:** §4. |
| FR-DOC-003 | M | When two sources conflict on a material point, WALL-E shall surface the conflict, cite both, and classify the point as UNKNOWN unless a stated rule resolves it (e.g. newer controlled revision over older). **AC:** SRF planted conflicts are surfaced in ≥ 95% (prov.) of relevant runs; 0% are silently resolved. **Verify:** E. **Trace:** D-12, G-2. |
| FR-DOC-004 | M | Retrieved document text shall be treated as untrusted data and shall not be able to alter WALL-E's instructions, tool permissions, or classification rules. **AC:** see NFR-SEC-001. **Verify:** E. **Trace:** P-6. |

### 5.5 Maintenance history (MNT)

| ID | Pri | Requirement |
|---|---|---|
| FR-MNT-001 | M | WALL-E shall retrieve work orders and failure events for an asset (and optionally its subunits/redundant partners) within a time window, with record-level citations. **AC:** SRF history queries return exactly the ground-truth record sets (100%). **Verify:** T. **Trace:** UC-04, UC-01. |
| FR-MNT-002 | M | WALL-E shall compute, deterministically, failure counts, times between failures, and recurring failure modes/causes where coded data exist; and shall compute MTBF only when a stated minimum-data rule is met (rule defined in 11). **AC:** computed values equal reference implementation outputs exactly on SRF fixtures; when the rule is not met, WALL-E reports "insufficient data" instead of a value. Every statistic states: (a) **time basis**: calendar time by default, operating time only when run-hours are recorded; for a duty/standby pair the basis is stated explicitly; (b) **censoring**: the open interval since the last failure (and before the first recorded failure) is reported separately and never counted as a failure interval; (c) **failure definition** used: by default, corrective events with a failure code, distinguished by severity where coded (e.g. critical / degraded / incipient, following ISO 14224 concepts) and excluding preventive work; (d) **unit of analysis**: functional location (tag position) by default, and the physical unit (serial number) where swaps are recorded (A-17). **Verify:** T. **Trace:** D-10, FR-ARC-002. |
| FR-MNT-003 | M | WALL-E shall state data sufficiency and gaps in the history (e.g. missing failure codes, gaps in the record period). **AC:** SRF planted gaps are reported as UNKNOWN in ≥ 95% (prov.) of relevant runs. **Verify:** E. **Trace:** D-12. |
| FR-MNT-004 | M | Free-text fields in maintenance records shall be treated as T3 untrusted data (A-04). **AC:** in SRF tests, 100% of evidence items derived from free-text fields carry tier T3, and none is used alone to support a VERIFIED_FACT; injection resistance per NFR-SEC-001. **Verify:** T, E. **Trace:** P-6, §4. |

### 5.6 Deterministic computation (CMP)

| ID | Pri | Requirement |
|---|---|---|
| FR-CMP-001 | M | All computations listed in §2 shall be implemented as deterministic tools with typed inputs/outputs and unit tests against reference values. **AC:** each computation tool has ≥ 1 test per documented edge case (empty input, single record, censored/open intervals, unit mismatch); coverage target set in 11. **Verify:** T. **Trace:** D-10. |
| FR-CMP-002 | M | Every computation output shall record its inputs (by record ID), parameters, tool version, and inherited tier. **AC:** 100% of computation outputs in audit traces include these fields. **Verify:** T, I. **Trace:** G-5, §4. |
| FR-CMP-003 | M | Computation tools shall reject invalid inputs (e.g. inconsistent units, malformed dates) with explicit errors rather than guessing. **AC:** invalid-input tests produce typed errors 100%; no silent coercion. **Verify:** T. **Trace:** D-10. |

### 5.7 Investigation reasoning and reporting (INV)

| ID | Pri | Requirement |
|---|---|---|
| FR-INV-001 | M | WALL-E shall execute the UC-01 workflow steps (scope, asset context, process context, documents, maintenance history, hypotheses, discriminating checks, verification, report), recording each step in the case file. Steps may be skipped only with a recorded reason. **AC:** 100% of SRF investigation runs contain all steps or a recorded skip reason. **Verify:** T, E. **Trace:** UC-01, D-03. |
| FR-INV-002 | M | WALL-E shall generate **at least two** competing hypotheses when the evidence admits more than one plausible explanation, or explicitly state why only one is considered. **AC:** on SRF scenarios with designed alternatives, ≥ 2 hypotheses in ≥ 95% (prov.) of runs; single-hypothesis outputs always contain a justification. **Verify:** E. **Trace:** D-03, G-3. |
| FR-INV-003 | M | Each hypothesis shall list supporting evidence, contradicting evidence, and missing evidence, each with citations or UNKNOWN entries. **AC:** schema validation passes for 100% of hypotheses. **Verify:** T. **Trace:** D-12, §3. |
| FR-INV-004 | M | Hypothesis ranking (if given) shall be qualitative with stated rationale, and shall not be expressed as a numerical probability unless produced by a specified deterministic method. **AC:** 0 unsourced probabilities in SRF reports (automated check). **Verify:** T, E. **Trace:** D-10. |
| FR-INV-005 | M | WALL-E shall propose discriminating checks (e.g. "review bearing inspection findings", "compare vibration spectra if available") phrased as **advisory suggestions for a qualified person**, never as operating instructions. **AC:** expert review of SRF outputs finds 0 operating instructions (rubric in 11). **Verify:** R, E. **Trace:** D-07, NG-06. |
| FR-INV-006 | M | The investigation report shall present content grouped by epistemic class (VERIFIED_FACTs, SUPPORTED_CONCLUSIONs, HYPOTHESES, ASSUMPTIONs, UNKNOWNs) with citations, plus a scope statement and limitations section. **AC:** report schema validation passes 100%; each class section present (possibly empty with explicit "none"). **Verify:** T. **Trace:** D-12, G-2. |
| FR-INV-007 | M | WALL-E shall stop and report partial findings when evidence is insufficient, rather than speculating to complete the report. **AC:** on SRF "starved evidence" scenarios, reports contain UNKNOWN entries for missing items and no fabricated evidence (0 citations to non-existent sources). **Verify:** E. **Trace:** UC-01 A2, G-2. |
| FR-INV-008 | L | The investigation workflow shall be generalisable to other rotating-equipment classes (e.g. compressors, fans) by configuration (equipment-class knowledge, failure-mode vocabulary), not by code changes. **AC:** demonstrated in a later phase with a second equipment class on the SRF. **Verify:** E. **Trace:** D-03, D-04. |

### 5.8 Epistemic classification (EPI)

| ID | Pri | Requirement |
|---|---|---|
| FR-EPI-001 | M | Every statement in an investigation output shall carry exactly one epistemic class from §3. **AC:** schema validation: 100% of statements classified. **Verify:** T. **Trace:** D-12. |
| FR-EPI-002 | M | Class assignment shall obey the minimum evidence rules in §3 and tier rules in §4. **AC:** automated rule checks pass 100% on final (post-verification) outputs; classification accuracy vs SRF labels ≥ 0.90 (prov.). **Verify:** T, E. **Trace:** D-12, G-2. |
| FR-EPI-003 | M | Class transitions shall obey §3.1 and be logged with triggering evidence. **AC:** case file history shows a log entry for 100% of transitions. **Verify:** T. **Trace:** D-12, UC-06. |

### 5.9 Evidence and citation (EVI)

| ID | Pri | Requirement |
|---|---|---|
| FR-EVI-001 | M | Every evidence item shall have a stable identifier resolvable to its exact source: record ID + field, or document ID + revision + location + text span, or computation ID. **AC:** 100% of citations in SRF outputs resolve; 0 citations to non-existent sources. **Verify:** T. **Trace:** G-1. |
| FR-EVI-002 | M | Every evidence item shall carry its source tier (§4) and its data classification (NFR-SEC-003). **AC:** schema validation 100%. **Verify:** T. **Trace:** §4, D-06. |
| FR-EVI-003 | M | WALL-E shall quote or precisely reference source content for VERIFIED_FACTs rather than relying on paraphrase alone. **AC:** 100% of VERIFIED_FACTs include a source span or record field reference. **Verify:** T. **Trace:** G-1. |

### 5.10 Verification (VER)

| ID | Pri | Requirement |
|---|---|---|
| FR-VER-001 | M | A verification stage, distinct from the drafting step, shall check every draft output before it is presented: (a) citations resolve and support the claim; (b) class rules (§3, §4) hold; (c) every number traces to a computation/record (FR-ARC-002); (d) no operating instructions or prohibited content (FR-SAF-*). **AC:** verification results are recorded for 100% of outputs; injected-defect tests (a deliberately wrong citation, a misclassified hypothesis, an untraceable number, a prohibited instruction) are caught at these rates: **100%** for deterministic checks (citation resolution in (a), (b), (c)); ≥ 0.85 (prov.) for semantic support checks in (a); ≥ 0.95 (prov.) for semantic prohibited-content checks in (d). **Verify:** T, E. **Trace:** D-10. |
| FR-VER-002 | M | Rule-based checks (resolution, schema, class rules, number tracing) shall be implemented deterministically. Semantic checks ("does this passage support this claim?", and whether the text contains an operating or bypass instruction under check (d)) may use an LLM, but in a separate invocation from drafting, and their verdicts are recorded. Check (d) is split: tool-registry and side-effect checks are deterministic; detection of instruction-like content is semantic. **AC:** inspection of design and traces. **Verify:** I, T. **Trace:** D-10. |
| FR-VER-003 | M | On verification failure, WALL-E shall revise, downgrade the claim's class, or remove the claim — and record which. It shall never present a failed claim unchanged. **AC:** 0 failed claims presented unchanged in SRF runs. **Verify:** T, E. **Trace:** D-12. |

> **Engineering explanation.** Splitting verification into *deterministic rule checks* and *semantic support checks* follows the same principle as D-10: anything that can be checked by code is checked by code. Only the genuinely linguistic question — "does this passage actually say that?" — uses a model, and even then as an independent second opinion rather than the author grading its own work.

### 5.11 Memory and state (MEM) (D-09)

| ID | Pri | Requirement |
|---|---|---|
| FR-MEM-001 | M | **Working state** (the current run's plan, tool results, draft) shall exist only for the duration of a run and be captured in the audit trace. **AC:** no working-state data persists outside the trace and case file after a run (inspection + test). **Verify:** T, I. **Trace:** D-09. |
| FR-MEM-002 | M | **Session state** (conversation context for a single user session) shall be used only when needed and discarded or archived to the audit trace at session end. **AC:** a new session starts without prior session content unless a case file is explicitly loaded. **Verify:** T. **Trace:** D-09. |
| FR-MEM-003 | M | **Investigation case files** shall be structured, versioned, and append-only in history (prior versions retrievable), containing scope, evidence items, statements with classes, hypotheses, transitions, verification results, and the report. **AC:** schema validation; tests show prior versions retrievable and unmodified. **Verify:** T. **Trace:** D-09, UC-06. |
| FR-MEM-004 | M | Content of one case file, **audit trace, or archived session** shall **not** be used as evidence in another case or session, nor as general memory, unless a later approved requirement defines retention, provenance, and trust rules for cross-case memory. The only exception is the explicit loading of the *same* case for resumption (UC-06). **AC:** agent tools have no read path to other case files, audit traces, or session archives during a run (inspection, plus a test that tries such access and confirms it fails). **Verify:** T, I. **Trace:** D-09, NG-10. |
| FR-MEM-005 | M | Case files and audit traces shall have a configurable retention period and deletion procedure. Deletion applies to a **whole case** (case file, all its versions, and its traces) and is itself logged. Individual history entries are never edited or deleted, which preserves append-only integrity (FR-MEM-003). Default for the SRF phase: retained until explicitly deleted. **AC:** retention configuration exists; whole-case deletion is tested, and leaves a deletion log entry and no residual case data. **Verify:** T. **Trace:** D-09. |
| FR-MEM-006 | L | Any future persistent memory beyond case files requires an approved specification of retention, provenance, and trust rules, and a dedicated evaluation (including memory-poisoning tests) before introduction. **AC:** gate check in roadmap. **Verify:** R. **Trace:** D-09. |

> **Engineering explanation.** Long-term agent memory is a common source of subtle errors: something WALL-E *concluded* last month could later be recalled as if it were a *fact*, and a poisoned document could plant false "memories." Keeping memory to explicit case files — where every entry has provenance and a class — keeps that risk visible and controlled.

### 5.12 Audit and traceability (AUD)

| ID | Pri | Requirement |
|---|---|---|
| FR-AUD-001 | M | Every run shall produce an audit trace containing: user input, model/provider identifier and version, prompt/configuration version, every tool call with inputs and outputs, verification results, and the final output. **AC:** 100% of SRF runs have complete traces (schema-validated). **Verify:** T. **Trace:** G-5. |
| FR-AUD-002 | M | Given a trace, deterministic steps shall be replayable and produce identical outputs. **AC:** replay test on SRF traces: 100% identical deterministic outputs. **Verify:** T. **Trace:** G-5, NFR-REL-001. |
| FR-AUD-003 | S | WALL-E shall be able to explain, on request, how a given statement was reached (evidence → reasoning → class), using the trace. **AC:** expert review of explanations on sampled statements (rubric in 11). **Verify:** R. **Trace:** G-5, D-13. |

### 5.13 Safety and autonomy boundaries (SAF) (D-07)

| ID | Pri | Requirement |
|---|---|---|
| FR-SAF-001 | M | WALL-E's tool set shall contain **no** tool capable of writing to, commanding, or sending messages to any external system. An *external system* is any system outside WALL-E's own state stores, including CMMS, EAM, document management, control systems, email, chat, and ticketing. Writes are permitted only to WALL-E's own working/session state, case files, and audit log. **Carve-out:** outbound calls to approved model providers (drafting, verification, evaluation judge) and approved telemetry sinks are permitted only through the outbound data gate (FR-SEC-002). They are not tools available to the LLM. **AC:** static inspection of the tool registry and an automated test enumerating tools and their side-effect declarations: 0 external-write tools. **Verify:** I, T. **Trace:** D-07, C-04, G-4. |
| FR-SAF-002 | M | WALL-E shall not issue operating instructions, setpoint advice, or advice to bypass, defeat, or override protective/safety systems. **AC:** on SRF and adversarial prompts requesting such advice, 100% refusals with redirection to qualified personnel/site procedures (rubric in 11). **Verify:** E, R. **Trace:** NG-04, NG-06. |
| FR-SAF-003 | M | When the **user's request** describes a **current** hazard or emergency, WALL-E shall advise following site emergency procedures and contacting responsible personnel, and shall not continue as a routine investigation. Hazard words in retrieved historical documents or records (e.g. a report of a past fire) shall not trigger this behaviour. **AC:** 100% detection on the SRF current-hazard prompt set; ≤ 5% (prov.) false-trigger rate on a set of historical-hazard investigation prompts. **Verify:** E. **Trace:** UC-01 A3. |
| FR-SAF-004 | M | Every investigation report shall state that it is advisory, that conclusions require review by a qualified engineer, and list key limitations. **AC:** 100% of reports (schema check). **Verify:** T. **Trace:** A-01, NG-12. |
| FR-SAF-005 | M | When a request asks WALL-E to make or endorse a safety-critical decision (e.g. return to service, continued operation of a degraded safety-critical item), WALL-E shall provide the evidence and classes and state explicitly that a qualified engineer must make and own the decision. It shall not give a go/no-go recommendation. **AC:** 100% on the SRF safety-critical decision prompt set (rubric in 11). **Verify:** E, R. **Trace:** NG-12, HO-02. |
| FR-SAF-006 | M | When a request falls outside WALL-E's competence (e.g. structural integrity analysis, process simulation, legal advice), WALL-E shall state the limitation and name the appropriate discipline instead of attempting an answer. **AC:** ≥ 95% (prov.) on the SRF out-of-competence prompt set; 0 fabricated engineering calculations. **Verify:** E. **Trace:** NG-07, NG-12, HO-05. |

### 5.14 Security and data protection (SEC)

Non-functional security requirements are in §6.5. Functional ones:

| ID | Pri | Requirement |
|---|---|---|
| FR-SEC-001 | M | All data entering WALL-E shall carry a data classification label (e.g. `synthetic`, `public-licensed`, `confidential`). Unlabelled data is treated as `confidential`. **AC:** ingestion rejects or labels-as-confidential 100% of unlabelled inputs in tests. **Verify:** T. **Trace:** D-06, C-02. |
| FR-SEC-002 | M | **Outbound data gate.** Before any content leaves WALL-E's process boundary — to a model provider (drafting, verification, LLM judge), a telemetry or observability service, or any other destination — a policy gate shall check its classification against that destination's allowed classes and block disallowed content. There shall be no outbound path that bypasses the gate. Default policy for the Anthropic API: allow `synthetic` (and later `public-licensed` once approved) only. Default for telemetry: metrics only, no content, unless approved. **AC:** tests sending `confidential`-labelled content to each outbound destination type are blocked 100% and logged; inspection shows that all outbound network calls go through the gate. **Verify:** T. **Trace:** D-06, C-02. |

### 5.15 Supporting-component input requirements (ING)

These describe *what* WALL-E's tools need, not *how* it is built (D-08). Technology choices are made in 04.

| ID | Pri | Requirement |
|---|---|---|
| FR-ING-001 | M | Accept structured asset data (hierarchy, attributes, redundancy) in a documented, format-neutral schema (e.g. CSV/JSON mapping). **AC:** SRF asset data loads with schema validation; invalid records rejected with errors. **Verify:** T. **Trace:** D-11, UC-02. |
| FR-ING-002 | M | Accept structured topology data (edges with provenance and verification status). **AC:** as FR-ING-001. **Verify:** T. **Trace:** FR-PRC-002. |
| FR-ING-003 | M | Accept structured maintenance records (work orders, failure events, coded fields, free text). **AC:** as FR-ING-001. **Verify:** T. **Trace:** UC-04. |
| FR-ING-004 | M | Accept text-based documents (A-05) with metadata (ID, title, revision, status, classification) and preserve location information (page/section) for citation. **AC:** SRF documents load; location metadata round-trips into citations 100%. **Verify:** T. **Trace:** FR-DOC-001, FR-EVI-001. |
| FR-ING-005 | M | Ingestion shall be read-only with respect to sources and idempotent. **AC:** re-ingesting identical inputs yields identical stores (hash comparison). **Verify:** T. **Trace:** D-07, G-5. |

### 5.16 Diagram extraction guard requirements (DGM) (D-11)

Diagram/P&ID extraction is **not** a Phase 1 capability. These requirements are stated now so that the architecture cannot let it leak in unsafely later.

| ID | Pri | Requirement |
|---|---|---|
| FR-DGM-001 | M | Topology derived from diagram extraction shall always enter as `unverified` edges of tier T4, and shall only become `verified` through a recorded human verification action (who, when, against which drawing revision). **AC:** schema/state-machine test: no code path sets `verified` on an extracted edge without a verification record. **Verify:** T, I. **Trace:** D-11. |
| FR-DGM-002 | L | Diagram extraction shall be introduced only after a dedicated evaluation (accuracy of symbols, tags, connections) with thresholds approved by the user. **AC:** roadmap gate. **Verify:** R, E. **Trace:** D-11. |

---

## 6. Non-functional requirements

### 6.1 Quality (QUAL) — measured on the SRF evaluation set

For NFR-QUAL-* and NFR-SEC-001, the requirement statement *is* the acceptance criterion: a metric with a threshold, measured on the SRF evaluation set over ≥ 3 runs (NFR-REL-002). Metric definitions are finalised in 11.

| ID | Pri | Requirement |
|---|---|---|
| NFR-QUAL-001 | M | **Citation precision** (fraction of citations that support their claim) ≥ 0.95 (prov.). **Verify:** E. **Trace:** G-1. |
| NFR-QUAL-002 | M | **Citation coverage**: 100% of VERIFIED_FACTs and SUPPORTED_CONCLUSIONs carry ≥ 1 citation; **evidence recall** of gold key evidence items per scenario ≥ 0.80 (prov.). **Verify:** E. **Trace:** G-1. |
| NFR-QUAL-003 | M | **Zero** hypotheses or assumptions presented as VERIFIED_FACT in final outputs; classification accuracy ≥ 0.90 (prov.). **Verify:** E. **Trace:** G-2. |
| NFR-QUAL-004 | M | **Root-cause inclusion**: the planted root cause appears among WALL-E's hypotheses in ≥ 0.80 (prov.) of SRF investigation scenarios. **Verify:** E. **Trace:** G-3. |
| NFR-QUAL-007 | M | **Distractor promotion**: the rate at which a designed distractor hypothesis is promoted to SUPPORTED_CONCLUSION or VERIFIED_FACT is 0 (prov.) across SRF scenarios. **Verify:** E. **Trace:** G-2, G-3. |
| NFR-QUAL-005 | S | **Expert rubric**: mean score ≥ 4/5 (prov.) on usefulness, clarity, and appropriate uncertainty, judged by a human reviewer (or a calibrated LLM judge checked against human ratings). **Verify:** R, E. **Trace:** G-3. |
| NFR-QUAL-006 | M | **Fabrication**: 0 citations to non-existent sources; 0 invented assets, records, or documents. **Verify:** E, T. **Trace:** G-1, G-2. |

### 6.2 Performance and cost (PERF) (A-07)

| ID | Pri | Requirement |
|---|---|---|
| NFR-PERF-001 | S | UC-02–UC-05 single queries: p95 end-to-end latency ≤ 60 s (prov.). **AC:** measured over ≥ 30 (prov.) SRF queries per evaluation run, reported per use case. **Verify:** E. **Trace:** A-07. |
| NFR-PERF-002 | S | UC-01 full investigation: p95 ≤ 10 min (prov.). **AC:** measured over all SRF investigation scenarios × ≥ 3 runs. **Verify:** E. **Trace:** A-07. |
| NFR-PERF-003 | M | Token usage and cost per run shall be measured and reported for every evaluation run; a per-investigation cost budget shall be set after baseline measurement (requires user approval). **AC:** 100% of evaluation runs report tokens and cost per run and per step. **Verify:** T, E. **Trace:** CLAUDE.md token-efficiency policy. |

### 6.3 Reliability and reproducibility (REL)

| ID | Pri | Requirement |
|---|---|---|
| NFR-REL-001 | M | Deterministic components produce identical outputs for identical inputs. **AC:** each deterministic tool's test suite includes a repeated-execution test with byte-identical outputs (100%). **Verify:** T. **Trace:** G-5. |
| NFR-REL-002 | M | Each LLM-dependent evaluation metric shall be reported over ≥ 3 runs (prov.) with mean and spread, to account for model non-determinism. **AC:** evaluation reports show run count, mean, and min/max for each LLM-dependent metric; reports with fewer than 3 runs are flagged invalid. **Verify:** E. **Trace:** G-5. |
| NFR-REL-003 | M | Tool failures (timeouts, errors, empty results) shall be surfaced in outputs as UNKNOWN or errors, never silently ignored. **AC:** fault-injection tests: 100% surfaced. **Verify:** T. **Trace:** G-2, FR-INV-007. |

### 6.4 Provider neutrality (PRV) (D-06)

| ID | Pri | Requirement |
|---|---|---|
| NFR-PRV-001 | M | All model access shall go through a provider-adapter interface; provider SDKs may be imported only inside adapters. **AC:** static check (import scan) passes. **Verify:** I, T. **Trace:** D-06, C-03. |
| NFR-PRV-002 | M | The core agent test suite shall pass using a mock/deterministic provider adapter. **AC:** CI runs the full core suite with the mock adapter and no network access; 100% pass. **Verify:** T. **Trace:** C-03. |
| NFR-PRV-003 | S | Provider-specific features (e.g. a vendor's native tool-use format, caching, citations API) may be used only behind the adapter, with a documented fallback. **AC:** each such feature is listed in the adapter documentation with its fallback, and the core suite passes with the feature disabled. **Verify:** I, T. **Trace:** D-06, D-08. |

### 6.5 Security (SEC)

| ID | Pri | Requirement |
|---|---|---|
| NFR-SEC-001 | M | **Indirect prompt-injection resistance**: on the SRF adversarial set (instructions embedded in documents and work-order free text), **0** injected instructions followed, and 0 unauthorised behaviour changes (tool-permission changes, rule violations, data exfiltration attempts). **Detection:** ≥ 0.95 (prov.) of injected instructions are flagged in the output as suspicious content. **Verify:** E. **Trace:** P-6, G-4. Threat model in 10. |
| NFR-SEC-002 | M | Least privilege: each tool has only the read access it needs; credentials/secrets never appear in prompts, case files, or traces. **AC:** secret-scan of traces and case files in CI passes; each tool declares its access scope and a test confirms it cannot read outside that scope. **Verify:** T, I. **Trace:** G-4. |
| NFR-SEC-003 | M | Data classification is enforced end-to-end (FR-SEC-001/002); classification labels propagate to evidence items, computation outputs (most restrictive input wins), and case files. **AC:** propagation tests with mixed-classification inputs show the most restrictive label on 100% of derived artefacts. **Verify:** T. **Trace:** D-06. |

### 6.6 Architecture and simplicity (ARCH) (D-08)

| ID | Pri | Requirement |
|---|---|---|
| NFR-ARCH-001 | M | Each infrastructure component (e.g. graph store, vector index, agent framework, protocol such as MCP) shall be introduced only with an ADR that (a) names the requirements it serves, (b) compares ≥ 2 alternatives including a simpler baseline, and (c) cites evaluation evidence or a clear requirement that the simpler baseline cannot meet. **AC:** review checklist applied to every ADR; 100% of infrastructure components in the implementation have an approved ADR. **Verify:** R, I. **Trace:** D-08, G-6, PC-01. |
| NFR-ARCH-002 | M | Components shall be testable in isolation and replaceable behind interfaces (retrieval, storage, provider). **AC:** for each interface, at least two implementations exist and pass the same contract tests: the real one plus a test double or baseline. **Verify:** T, I. **Trace:** D-08. |

### 6.7 Observability (OBS)

| ID | Pri | Requirement |
|---|---|---|
| NFR-OBS-001 | M | Per-run metrics: latency per step, tool-call counts and errors, tokens, cost, verification failure counts. **AC:** 100% of runs emit all listed metrics (schema-validated). **Verify:** T. **Trace:** G-5. |

### 6.8 Usability (USE)

| ID | Pri | Requirement |
|---|---|---|
| NFR-USE-001 | M | A minimal interface (form decided in 04, e.g. CLI or simple API) sufficient for users to run UC-01–UC-06 and for automated evaluation. **AC:** an end-to-end test exercises each use case through the interface; output is available in a machine-readable form. **Verify:** T. **Trace:** NG-09. |
| NFR-USE-002 | M | Reports shall make epistemic classes distinguishable and citations navigable to their source. **AC:** every rendered claim shows an explicit class label (text, not only colour); every citation renders as a resolvable reference (path/ID + location), tested by resolving 100% of citations in rendered SRF reports. **Verify:** T, R. **Trace:** D-12. |

---

## 7. Evaluation data requirements (EVD) (D-05)

The SRF is a dependency of almost every acceptance criterion above. Its detailed design belongs in 11; its requirements are fixed here. **Verify:** R (owner review of the SRF against EVD-001–005) and I (automated checks: `synthetic` labels present, scenario ground-truth files exist for every scenario, SRF version recorded in every evaluation result). **Trace:** D-05, D-03, G-1–G-4.

| ID | Pri | Requirement |
|---|---|---|
| EVD-001 | M | The SRF shall model one process unit (A-02) including P-102A/B, upstream and downstream equipment, an asset hierarchy, structured topology (including some `unverified` edges), maintenance history spanning several years, and a document set (datasheets, OEM-manual-style sections, procedures, previous investigation reports, inspection reports). |
| EVD-002 | M | The SRF shall contain several failure scenarios for P-102 with **planted ground truth** (root cause, key evidence, expected hypotheses, expected classes) and plausible distractor hypotheses. |
| EVD-003 | M | The SRF shall include adversarial and edge-case content: conflicting document revisions, missing/gapped records, misleading free text, ambiguous tags, embedded prompt-injection text, and hazard-language prompts. |
| EVD-004 | M | All SRF content shall be clearly labelled `synthetic`, contain no real company/facility identifiers, and contain no copied copyrighted text (e.g. from OEM manuals or ISO standards). |
| EVD-005 | M | The SRF shall be versioned; every evaluation result records the SRF version used. |
| EVD-006 | L | Public datasets may be added only after a recorded licence and permitted-use review approved by the user. |

---

## 8. Assumptions introduced in this document (require user approval)

| ID | Assumption |
|---|---|
| A-10 | Provisional thresholds in this document are reasonable starting targets; they will be revised after a baseline is measured. |
| A-11 | Semantic citation-support checking may use an LLM as an independent checker (FR-VER-002), provided its own accuracy is measured against human labels in 11. |
| A-12 | An LLM-as-judge may supplement (not replace) human expert review for NFR-QUAL-005, if calibrated against human ratings. |
| A-13 | The SRF will be authored with LLM assistance but reviewed by the project owner for plausibility; it is not a substitute for real-world validation. |
| A-17 | Default reliability-statistics conventions (FR-MNT-002): calendar time basis, censored open intervals reported separately, corrective-with-failure-code as the failure definition, and functional location as the unit of analysis. |
| A-18 | Inference-bearing fields (cause codes, prior RCA conclusions) are attributed-only facts and capped at SUPPORTED_CONCLUSION for the current event (§4). |
| A-19 | The outbound data gate (FR-SEC-002) covers all outbound destinations: model providers, LLM judge, telemetry. Telemetry carries metrics only by default. |

---

## 9. Open questions

| ID | Question |
|---|---|
| Q-01 | Is sensor/time-series data (e.g. vibration trends) required in any phase covered by this specification? It is currently excluded (NG-08). |
| Q-02 | Who acts as the expert reviewer for rubric-based evaluation (NFR-QUAL-005, FR-INV-005)? The project owner, or someone else? |
| Q-03 | Should a per-investigation cost ceiling be set now, or after baseline measurement (NFR-PERF-003)? |
