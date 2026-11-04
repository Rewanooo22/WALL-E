# Phase 1 Specification — Multi-discipline Document Intelligence

| Field | Value |
|---|---|
| Status | **APPROVED — M0 (2026-11-04)** |
| Path | `docs/spec/phase-1-document-intelligence.md` |
| Governs | Phase 1 implementation (M1–M7) |
| Related | `01-agent-charter.md`, `02-requirements.md`, `03-capabilities-boundaries.md` (v0.1); `docs/adr/ADR-001-phase1-deterministic-baseline.md` |

**Labels.** **[C]** confirmed by the project owner · **[A]** assumption · **[R]** recommendation in this draft, awaiting approval.

---

## 1. Product statement and Phase 1 purpose

**[C]** WALL-E is an **internal, evidence-grounded, multi-discipline engineering and project execution assistant**. Its initial scope is document intelligence across **Mechanical, Piping, Fabrication, Installation, and Electrical & Instrumentation (E&I)**.

**[C]** Phase 1 delivers a **usable, deterministic document-analysis pipeline**. It is not a chatbot and not an agent framework.

**[C]** Phase 1 is a **CLI-based internal prototype**. Any user-facing interface (web UI, desktop UI, server, API) is outside Phase 1 scope.

Given a project folder (a manifest and its documents), Phase 1 produces an evidence-grounded report with exactly these sections:

1. Project Summary
2. Document Register
3. Discipline-based Scope Breakdown
4. Missing Information
5. Document Conflicts and Revision Issues
6. Preliminary Technical Observations
7. Coverage *(added; required for honest reporting)*
8. Limitations *(added; fixed and rule-generated)*

---

## 2. Precedence over 01–03

**[R]** Where this document conflicts with `01`–`03` v0.1, **this document governs for Phase 1**. Maintenance-specific items in 01–03 (D-02, D-03, UC-01–UC-06, FR-AST-\*, FR-PRC-\*, FR-MNT-\*, FR-INV-\*, EVD-001/002, A-02) are **inactive** for Phase 1. They will be revisited in the v0.2 rewrite after Phase 1. Cross-cutting requirements reused from 02 are listed in §17. The banner text for 01–03 is in Appendix A and has been applied to those documents.

---

## 3. Phase 1 non-goals

| ID | Non-goal | Source |
|---|---|---|
| P1-NG-01 | Quantity take-off, quantity verification, or any arithmetic on quantities | [C] |
| P1-NG-02 | Cost estimation, pricing, or processing of BOQ rate/amount columns | [C] |
| P1-NG-03 | Scheduling, durations, sequencing, resource planning | [C] |
| P1-NG-04 | Engineering design approval, adequacy judgements, code-compliance determinations | [C] |
| P1-NG-05 | Maintenance and troubleshooting workflows | [C] |
| P1-NG-06 | CAD geometry, symbol, or dimension interpretation; native CAD files (DWG/DXF) | [C] |
| P1-NG-07 | OCR of image-only pages | [R] |
| P1-NG-08 | Any LLM use, network access, or external API call | [C] (S-4) |
| P1-NG-09 | User-facing interface, server, or API | [C] |
| P1-NG-10 | Writes to any system other than the run output directory | D-07 |
| P1-NG-11 | Inferring the company's execution responsibility from document content | [C] |
| P1-NG-12 | Attributing responsibility for individual gaps or conflicts to a party | [R] (see Q-P1-01) |

---

## 4. Inputs

### 4.1 Supported files **[C]**

| Type | Phase 1 handling |
|---|---|
| Text-based PDF (specifications, datasheets, project documents) | Page text, word positions, tables |
| PDF drawings with an accessible text layer | Title block fields, revision tables, text and table layers. **No geometry.** |
| Excel `.xlsx` (BOQs, registers, lists) | Cell values with sheet and cell locators |

Everything else (scanned or image-only pages, `.xls`, `.docx`, DWG/DXF, images, encrypted PDFs) is **reported in Coverage as unsupported or unreadable**. It is never skipped silently.

### 4.2 Project manifest `project.json` **[C]/[R]**

The manifest is the **only** source of project conventions. WALL-E has no built-in company conventions.

```json
{
  "schema_version": "1.0",
  "project_id": "SYN-001",
  "title": "Cooling water pump replacement and piping modification",
  "description": "Free text provided by the user.",
  "delivery_model": "CLIENT_DESIGNED",
  "delivery_model_notes": null,
  "contracted_scope": {
    "declared_by": "user",
    "disciplines": ["Mechanical", "Piping", "Installation"],
    "basis": [{"file": "contract/scope-of-work.pdf", "page": 3}],
    "notes": null
  },
  "default_classification": "confidential",
  "files": [
    {"path": "docs/PMP-SYN001-PI-SPC-001_RevB.pdf", "classification": "synthetic"}
  ],
  "conventions": {
    "document_number_pattern": null,
    "discipline_codes": null,
    "tag_pattern": null,
    "revision_sequence": null,
    "execution_issue_statuses": null,
    "boq_columns": null
  }
}
```

| Field | Rules |
|---|---|
| `project_id` | Required; namespaces every ID; must match `^[A-Za-z0-9_-]{1,64}$`. |
| `description` | Optional. Recorded as **user-report evidence (tier T3)**, shown as "Declared by user". Never a fact. |
| `delivery_model` | **[C]** One of `CLIENT_DESIGNED`, `DESIGN_AND_BUILD`, `HYBRID`. Absent or invalid → reported as **UNKNOWN**. See §5. |
| `delivery_model_notes` | **[R]** Recommended for `HYBRID`, to describe the split. If `HYBRID` is declared without notes, the design-responsibility split is reported as UNKNOWN. |
| `contracted_scope` | **[C]** The disciplines the company is contracted to execute. Declared by the user, optionally citing contract/scope documents (file + page). Absent → "Contracted execution scope: not declared (UNKNOWN)". See §6. |
| `classification` | Per file. Unlabelled files take `default_classification`, which itself defaults to `confidential` (FR-SEC-001). |
| `conventions.*` | All optional. If a convention is absent, every feature that depends on it reports **UNKNOWN or "not evaluated"** instead of guessing. |

**Engineering explanation.** Numbering schemes, discipline codes, revision sequences and status vocabularies differ between clients and between projects. A built-in default would quietly turn one organisation's conventions into "facts" about another project's documents. Making them explicit manifest inputs keeps every interpretation traceable to a human declaration.

---

## 5. Project delivery model **[C]**

| Value | Meaning recorded in the report |
|---|---|
| `CLIENT_DESIGNED` | User declares the design is provided by the client (or the client's engineer); the company executes to that design. |
| `DESIGN_AND_BUILD` | User declares the company holds design and execution responsibility under its contract. |
| `HYBRID` | User declares responsibility is split; the split is described in `delivery_model_notes` or reported as UNKNOWN. |

Rules:

- The delivery model is a **user declaration** (T3 user-report evidence). It is rendered as "Declared by user in project manifest" and is never presented as a fact derived from contract documents. If `contracted_scope.basis` cites documents, those citations are shown alongside, but WALL-E does not interpret contract wording in Phase 1.
- The Project Summary shows the delivery model together with this fixed statement: *"The delivery model describes the declared responsibility boundary between parties. It does not give WALL-E authority to approve, certify, or accept any engineering design, under any delivery model."*
- **[R]** In Phase 1 the delivery model is **displayed only**. It does not change any analysis rule, and it is not used to assign responsibility for gaps or conflicts (P1-NG-12; open question Q-P1-01).

---

## 6. Document discipline vs contracted execution scope **[C]**

These are **two distinct concepts and are never derived from each other.**

| Concept | Definition | Source |
|---|---|---|
| **Document discipline** | The discipline a document belongs to. | (a) An explicit discipline field in the title block or register, cited; or (b) the manifest `discipline_codes` rule applied to the document number (SUPPORTED_CONCLUSION citing the rule). Otherwise **"unassigned"**. |
| **Contracted execution scope** | The disciplines the company is contracted to execute. | **Only** `contracted_scope` in the manifest (a user declaration, with optional citations). |

Rules:

- **P1-DSC-R1:** The presence of documents for a discipline is **never** reported as, or used to imply, contracted responsibility for that discipline.
- **P1-DSC-R2:** Section 3 shows a matrix: *discipline · documents found (count, cited) · contracted per manifest (Yes / No / Not declared)*.
- **P1-DSC-R3:** If a discipline is contracted but no documents of that discipline were found → **Missing Information** item (MI-08), stating the scope of the search.
- **P1-DSC-R4:** If documents exist for a discipline that is not declared as contracted → an **informational** row only: *"Documents present; not declared as contracted scope."* It is not a gap or a conflict, and it carries no recommendation.
- **P1-DSC-R5:** If `contracted_scope` is absent, the contracted column reads "Not declared" for every discipline, and MI-08 is not evaluated.

---

## 7. Report section definitions

Every statement in sections 1–6 is a **claim object** (§12) generated from a template. Free narrative text is not permitted.

### 7.1 Project Summary
Contents: project ID and title; user description (labelled "Declared by user"); delivery model with the fixed statement (§5); contracted scope (§6); counts of files processed, unsupported and unreadable; document counts by discipline and by type; revision-issue, missing-information and conflict counts, each linking to its section. **No synthesis or interpretation.**

### 7.2 Document Register
One row per **document identity** (document number + revision + sheet where applicable). Columns: document number, title, revision, date, status (raw value), discipline (+ basis), source file and pages, listed in the project register (Y/N/no register), identity status (`RESOLVED` / `UNRESOLVED` / `AMBIGUOUS`), current-revision status (`CURRENT` / `SUPERSEDED` / `UNKNOWN`) and its basis. Every field is cited.

### 7.3 Discipline-based Scope Breakdown
Per document discipline:
- the discipline/execution-scope matrix (§6);
- the documents assigned to the discipline;
- **scope clauses**: text under headings that match the scope-heading list (Appendix B.3), quoted exactly with page citations;
- **BOQ lines** whose BOQ section or discipline column maps to the discipline (source transcription only, §8).

BOQ lines that cannot be mapped to a discipline are listed as "unassigned". They are never guessed.

### 7.4 Missing Information
Generated only by the rules in §9.1. Each item states the rule, the evidence, and the **search scope** (which files, pages and fields were examined).

### 7.5 Document Conflicts and Revision Issues
Generated only by the rules in §9.2–9.3. Every conflict cites **≥ 2 sources**, is classed **UNKNOWN**, and is **never resolved**.

### 7.6 Preliminary Technical Observations
Generated only by the explicit rules in §10. If no rule fires, the section says so, with the scope of the check.

### 7.7 Coverage
Every input file with its status (`PROCESSED`, `PARTIAL`, `UNSUPPORTED`, `ENCRYPTED`, `UNREADABLE`, `DUPLICATE`, `PARSE_FAILED`, `LIMIT_EXCEEDED`, `REJECTED_PATH`). Pages with no or unreliable text layers. Which checks ran, which were not evaluated (and why, e.g. a missing convention), and resolver results (§13).

### 7.8 Limitations
Fixed, rule-generated statements, including:
- deterministic rule-based analysis only;
- no engineering judgement or approval;
- BOQ transcription only;
- annotations and markups not read;
- image-only pages not read;
- free-text conflicts not detected;
- synthetic validation only (§15).

---

## 8. BOQ processing — source transcription only **[C]**

| Rule | Content |
|---|---|
| P1-BOQ-R1 | BOQ processing is **source transcription**. For each BOQ line WALL-E records **item number, description, unit, quantity** exactly as stated, each with a sheet + cell citation. |
| P1-BOQ-R2 | "Exactly as stated" means the cell's **stored value** plus its **displayed text** under the cell number format. Both are kept. The report shows the displayed text. No rounding, normalisation, unit conversion or reformatting. |
| P1-BOQ-R3 | Formula cells: the cached result is transcribed and flagged "formula-derived in source". If there is no cached result → **UNKNOWN** (MI-04). Formulas are never evaluated. |
| P1-BOQ-R4 | **No** sums, subtotal checks, quantity verification, plausibility checks, unit conversion, comparison with drawing BOM/MTO tables, or cost estimates. |
| P1-BOQ-R5 | Rate, amount, price and total columns, if present, are **not transcribed**. Coverage records "pricing columns present, not processed". |
| P1-BOQ-R6 | Column identification: use the manifest `boq_columns` if given; otherwise the default header list (Appendix B.4, **[A]**). If identification is ambiguous or fails → the sheet is **not transcribed**, and Coverage shows the candidates found. |
| P1-BOQ-R7 | Blank or non-numeric quantity, or blank unit → MI-04. The value is not inferred. |
| P1-BOQ-R8 | Every rendered quantity carries the label **"as stated in BOQ — not verified"**. |
| P1-BOQ-R9 | Merged cells are cited at their anchor cell. Hidden rows, columns and sheets are transcribed and flagged "hidden in source". |

---

## 9. Deterministic analysis rules

### 9.1 Missing information (MI)

| ID | Trigger | Class |
|---|---|---|
| MI-01 | A document listed in the project register is not among the supplied files (match by document number; revision handled by CR rules) | UNKNOWN (missing) |
| MI-02 | A document cited by a supplied document (reference pattern, Appendix B.2) is not supplied | UNKNOWN |
| MI-03 | A placeholder marker (Appendix B.1: TBD, TBA, TBC, HOLD, "by others", "later", "to be confirmed", "N/A?") appears in a value field or text | UNKNOWN, quoting the marker in context |
| MI-04 | A blank or uninterpretable required field: datasheet value cells adjacent to recognised attribute labels; BOQ quantity/unit; formula without a cached value | UNKNOWN |
| MI-05 | A title-block or register field (number, revision, title, date) is absent from a drawing or document | UNKNOWN |
| MI-06 | A page has no text layer, or an unreliable one | UNKNOWN; content not read |
| MI-07 | A file is unsupported, encrypted or failed to parse | UNKNOWN; content not read |
| MI-08 | A contracted discipline has no documents (only if `contracted_scope` is declared) | UNKNOWN |

There are **no** default "expected document" checklists (no invented conventions).

### 9.2 Revision issues (RV)

| ID | Trigger | Output |
|---|---|---|
| RV-01 | More than one revision of the same document number is supplied | List all, cited. Current revision decided only by RV-03. |
| RV-02 | The register's revision differs from the supplied file's revision | SUPPORTED_CONCLUSION: "register states X; file states Y". **Which is correct is UNKNOWN.** The register is a document too and may itself be out of date. |
| RV-03 | Determining the current revision | `CURRENT` / `SUPERSEDED` only from: (a) a revision table in the documents showing a later revision; (b) a register status of current or superseded; or (c) the manifest `revision_sequence`. Otherwise **UNKNOWN**. Label ordering (A < B) is never assumed. |
| RV-04 | A supplied document references another document at a revision different from the one supplied | SUPPORTED_CONCLUSION, both cited |
| RV-05 | The same document number and revision is supplied as two files with different content hashes | UNKNOWN (identity conflict) |

### 9.3 Attribute conflicts (CF)

| ID | Rule |
|---|---|
| CF-01 | **Scope:** only attribute–value pairs from tables and labelled fields (datasheets, specification tables, title blocks, registers). **Not** free text. **Not** BOQ quantities. |
| CF-02 | **Key:** (entity, attribute, qualifiers). The entity is a tag matched by the manifest `tag_pattern`, normalised by one documented rule (case-folding, removing spaces and hyphens: `P-201` = `P201`; `P-201A` ≠ `P-201`). If there is no `tag_pattern`, CF runs only on document-level attributes (e.g. title-block fields), and Coverage says so. |
| CF-03 | Attribute labels map through the glossary (Appendix B.5, **[A]**). Labels not in the glossary are **not compared**. |
| CF-04 | Qualifiers (design / operating / test; suction / discharge; min / max) are part of the key. Values with different qualifiers are never compared. |
| CF-05 | Units: same unit → exact compare. Different units of the same dimension → deterministic conversion (Appendix B.6), conflict if the relative difference exceeds the tolerance (Appendix B.6, **[R]**, decision P1-D-06). Ambiguous units (`bar` without g/a, `psi` without g/a, `hp`) → **NOT_COMPARABLE**. |
| CF-06 | Output: a conflict cites both (or all) sources, class **UNKNOWN**, text template "Sources state different values; WALL-E does not determine which governs." Non-comparable pairs are listed in Coverage. |
| CF-07 | Bias: precision over recall. Uncertain matches are not reported as conflicts. |

---

## 10. Preliminary Technical Observations — explicit rules **[C]/[R]**

**Purpose.** Observations are **cross-document findings an engineer would otherwise have to assemble by hand**. They do not restate any single document.

**Every observation must:**
1. come from a rule below (rule ID shown);
2. combine evidence from **≥ 2 documents**, or give a scoped absence across the document set;
3. cite all evidence used;
4. carry a fixed, reviewed "why it matters" sentence that is factual and not advisory.

| ID | Rule | Trigger | Output template | Class | Why it matters (fixed text) |
|---|---|---|---|---|---|
| OBS-01 | **Standards and editions matrix** | Standard designations (patterns in Appendix B.7) found in ≥ 1 document | Matrix: standard × documents citing it × edition/year as stated | VERIFIED_FACT per cell (quoted) | "Shows which standards the supplied documents cite, in one place." |
| OBS-02 | **Edition inconsistency** | The same standard is cited with different editions/years in different documents | "Standard S is cited as edition E1 in D1 and E2 in D2." | SUPPORTED_CONCLUSION; governing edition **UNKNOWN** | "Different editions can contain different requirements. WALL-E does not determine which edition governs." |
| OBS-03 | **Interdiscipline interface tags** | A tag (manifest `tag_pattern`) appears in documents of ≥ 2 different disciplines | "Tag T appears in Mechanical (D1 p.2) and E&I (D4 sheet X)." | SUPPORTED_CONCLUSION | "Items referenced by several disciplines are interface points between them." |
| OBS-04 | **Single-source tags** | A tag appears in exactly one supplied document | "Tag T appears only in D1 among the supplied documents." | SUPPORTED_CONCLUSION, scoped to supplied files | "Other documents referring to this item were not found among the supplied files." |
| OBS-05 | **Mixed unit systems** | The same glossary attribute is stated in SI units in some documents and US customary units in others | "Attribute A is stated in bar(g) in D1 and psig in D2." | SUPPORTED_CONCLUSION | "Mixed unit systems across documents require conversion during review." |
| OBS-06 | **Non-execution document status** | Only if `execution_issue_statuses` is declared: a document's status is not in the declared list | "D1 status 'IFA' is not among the declared execution-issue statuses." | SUPPORTED_CONCLUSION | "The document's status is not one the project declared as issued for execution." |
| OBS-07 | **Status values observed** | `execution_issue_statuses` not declared | Raw list of status values per document, uninterpreted | VERIFIED_FACT (quoted) | "Status values are listed as stated; WALL-E does not interpret them without a declared status vocabulary." |

**Excluded from observations** (forbidden by verifier rule V-07):
- restating or summarising a single document's content;
- judging adequacy, sufficiency, completeness of design or compliance;
- recommending design changes, materials or methods;
- safety judgements;
- generic advice (e.g. "ensure proper QA/QC");
- any statement that uses words from the forbidden-phrase list (Appendix B.8, e.g. "adequate", "compliant", "approved by WALL-E", "should use", "recommend").

**[R] Considered and rejected for Phase 1:** a design-condition collation matrix (which would largely rephrase datasheets), and an "expected documents" completeness check (which needs company conventions).

---

## 11. Evidence model and claim classes

### 11.1 Evidence
```
Evidence
  id            = sha256(project_id | file_sha256 | locator)[:16], prefixed with project_id
  project_id, file_path (relative), file_sha256
  locator       = {page, bbox?} | {sheet, cell | range}
  raw_text      exact extracted string
  norm_text     normalised (NFKC, whitespace collapsed, soft hyphens removed) — rules fixed and documented
  extractor     name + version
  quality       flags: TEXT_OK | TEXT_UNRELIABLE | HIDDEN_IN_SOURCE | FORMULA_DERIVED | MERGED_ANCHOR
```

### 11.2 Claims
```
Claim
  id, project_id, section, rule_id
  class         VERIFIED_FACT | SUPPORTED_CONCLUSION | HYPOTHESIS | ASSUMPTION | UNKNOWN
  statement     rendered from a template; every inserted value comes from cited evidence
  evidence_ids  [...], tier per evidence link (T1 structured register fields; T2 current controlled
                document; T3 superseded / uncontrolled / user-declared; T4 unused in Phase 1)
  assumption_ids [...]
  search_scope  required for absence claims (files, pages, fields examined)
  resolution    status from §13
```

- **Five classes retained** (S-2). Phase 1 emits mainly VERIFIED_FACT, SUPPORTED_CONCLUSION, ASSUMPTION and UNKNOWN. HYPOTHESIS is reserved (no Phase 1 rule emits it).
- **Display label:** VERIFIED_FACT is rendered as **"Fact as stated in source"**, to avoid implying engineering verification.
- Class and tier rules: 02 §3–§4 apply unchanged.

### 11.3 Unsupported, ambiguous and unresolvable evidence **[C]**

| Status | Meaning | How it is reported |
|---|---|---|
| `UNSUPPORTED_INPUT` | File type not supported, or file encrypted | Coverage + MI-07. No claims from it. |
| `UNREADABLE` | No text layer, or unreliable text layer (§12.3) | Coverage + MI-06. Text never used as fact evidence. |
| `PARSE_FAILED` / `LIMIT_EXCEEDED` | Parser error, timeout, or resource limit hit | Coverage + MI-07, with error class (no stack traces in the report). |
| `AMBIGUOUS` | More than one candidate value for a field (e.g. two document numbers on a page; ambiguous BOQ headers) | Claim class UNKNOWN, **listing all candidates with citations**. No candidate is selected. |
| `UNRESOLVED` | Document identity cannot be determined | Register row with identity UNRESOLVED; content still cited by file and page. |
| `NOT_COMPARABLE` | Conflict check impossible (ambiguous unit, unknown label, missing qualifier) | Coverage list; not a conflict. |
| `RESOLVER_FAIL` | Citation re-check failed (§13) | Claim **removed** from sections 1–6 and listed under "Verification failures" in Coverage. Run status `COMPLETED_WITH_VERIFICATION_FAILURES`; non-zero exit code. |
| `RESOLVER_DISAGREE` | Primary and cross-check extractors disagree (§13.2) | Claim kept, marked "extraction disagreement — check source", and listed in Coverage. |

---

## 12. Processing pipeline

```
[1 Load]      validate manifest; discover files; reject paths outside the project root and symlinks
              that escape it; sha256 every file; assign classification; detect duplicates
[2 Extract]   per file, in an isolated worker process (§14):
              PDF  → page text, words + bbox, tables, rotation, text-quality score
              XLSX → zip-size pre-check; cells (stored value, displayed text, formula flag,
                     merged anchor, hidden flags)
[3 Identify]  document number / revision / title / date / status / discipline from title blocks,
              first-page fields, register rows, manifest conventions
[4 Analyse]   register reconciliation, RV, MI, CF, BOQ transcription, scope clauses, OBS
[5 Claims]    template rendering → claim objects
[6 Verify]    rule checks (V-01..V-08) + independent citation resolver (§13)
[7 Report]    report.json (canonical), report.md (escaped), run_manifest.json →
              out/<project_id>/<run_id>/
```

### 12.3 Text quality
A page is `TEXT_UNRELIABLE` if, after extraction, the fraction of replacement characters, private-use code points, or non-printable characters exceeds a threshold (**[R]** 2%), or if the page has drawing content but fewer than N words (**[R]** N = 5; tuned on the development set only). Unreliable text is never used as fact evidence.

---

## 13. Verification and the citation resolver **[C]/[R]**

### 13.1 Rule checks (deterministic)

| ID | Check |
|---|---|
| V-01 | Every claim's evidence IDs exist and belong to the same `project_id` |
| V-02 | Class and tier rules (02 §3–§4) hold |
| V-03 | Every value inserted into a statement appears in its cited evidence (FR-ARC-002) |
| V-04 | Every conflict has ≥ 2 sources and class UNKNOWN |
| V-05 | Every absence claim has a non-empty `search_scope` |
| V-06 | No claim depends on a convention the manifest does not declare |
| V-07 | Section 6 claims use an OBS rule ID and contain no forbidden phrase (Appendix B.8) |
| V-08 | Report schema valid; all 8 sections present |

### 13.2 Independent citation resolver
For every cited evidence item, the resolver **re-opens the source file** (verifying its sha256 matches), re-extracts the text at the locator, and checks that the evidence's `norm_text` is contained in the re-extracted normalised text.

**[R] Independence measures:**
- **PDF:** re-extraction uses **pypdfium2 (the PDFium engine)**, not pdfminer.six (which the primary extractor, pdfplumber, uses). pypdfium2 is already a pdfplumber dependency, so no new package is needed.
- **XLSX:** re-extraction reads the workbook XML directly with Python's standard library (`zipfile` + `xml.etree`: shared strings, cell values) instead of openpyxl.

**Stated limitations (must appear in Coverage and README):**
1. The resolver **detects errors between extraction and reporting**: wrong page or cell, altered or truncated values, stale evidence, cross-project leakage, file changes after extraction.
2. Using a second engine catches **some** extractor-level errors. It **cannot** detect errors both engines share, e.g. a PDF whose embedded text layer itself is wrong (incorrect font encoding, text that differs from what is drawn on the page). Neither engine sees what a human sees.
3. Text-order differences between engines are tolerated by the containment check on normalised text. A containment check can pass even when the quoted text is ambiguous within the page (e.g. "10" appearing several times). The resolver therefore checks text, **not meaning or position**; bounding boxes are not cross-checked.
4. Displayed-text formatting in XLSX is derived by WALL-E from the number format. The stdlib reader checks the stored value only.
5. The resolver and the pipeline share the evidence model and normalisation rules. A bug in the normalisation rules affects both.
6. **Human spot-checking of citations remains necessary.** The resolver is a strong consistency check, not proof of correctness.

---

## 14. Security and parsing isolation **[C]/[R]**

### 14.1 What Phase 1 provides
| Control | Purpose | Strength |
|---|---|---|
| No network code; static import check; sockets disabled in test runs | Guarantees no data leaves via WALL-E's own code | Strong for WALL-E's code; **not** a sandbox against parser exploits |
| **Per-file worker subprocess** (`multiprocessing`, spawn) with wall-clock timeout, CPU and address-space limits (`resource.setrlimit`, Linux) | Contains hangs, memory blow-ups and crashes in parsers; one bad file cannot stop the run | Fault containment, **not** security isolation |
| In-worker socket guard (`socket.socket` replaced to raise) | Defence in depth against accidental network use by libraries | **Not** a security boundary; native code can bypass it |
| Pre-parse limits: file size, PDF page count, XLSX total uncompressed size and entry count (zip-bomb check) | Reject oversized or decompression-bomb inputs early | Partial |
| Path validation (no traversal, no escaping symlinks) | Keep each run inside its project root | Strong for path handling |
| Escaped Markdown rendering | Document text cannot inject links, HTML or fake sections into the report | Strong for report rendering |

### 14.2 What Phase 1 does **not** provide — explicit statement
- **Resource limits and subprocesses are not complete protection against malicious or malformed files.** PDF and XLSX parsers are complex; a crafted file could exploit a parser vulnerability and run code with the user's privileges, including network access.
- Phase 1 is **not** a hardened sandbox. True isolation (no-network namespace, unprivileged user, read-only filesystem, seccomp, or a container started with `--network=none`) is a **deployment-level control**. **[R]** It is documented in the README as the required operating mode for any non-synthetic documents. Phase 1 code does not implement it.
- **[R]** Phase 1 is intended only for documents from **trusted sources**, with pinned dependencies kept up to date.

### 14.3 Prompt injection
Phase 1 has no LLM, so instructions inside documents cannot change behaviour. Injected-instruction text stays in the fixtures, so the future LLM phase is tested against it from the start. Such text appears in the report only as escaped quoted evidence.

### 14.4 Process rule **[R]**
**No real or confidential documents may be uploaded to, pasted into, or processed in the cloud development session.** Development and testing use synthetic data only (C-01, D-06).

---

## 15. Datasets, the blind holdout, and metric reporting **[C]/[R]**

### 15.1 Development set
SYN-001 (multi-discipline; planted issues) and SYN-002 (isolation; overlapping document numbers), generated by `tests/fixtures/generate_dev.py` from `tests/fixtures/fixture_spec.md`, which includes the variation matrix (ADR-001 §6).

### 15.2 Blind holdout — independence protocol
| Step | Rule |
|---|---|
| H-1 | The holdout is authored in **M2, before any parser code exists**, and **before** the development ground truth is written. |
| H-2 | The author is a **separate subagent** whose input is limited to `fixture_spec.md` (variation categories, ground-truth schema, file-format rules). It is instructed not to read anything else in the repository. Its file-access log (tool calls) is captured and reviewed; the review result is recorded in `tests/holdout/PROVENANCE.md`. |
| H-3 | The author writes its own generator and ground truth. The parser developer **does not open** holdout files or truth until M7. |
| H-4 | At M2 the holdout files, generator and truth are sealed with a `SHA256SUMS` file committed alongside them; M7 verifies the seal before scoring. |
| H-5 | The holdout is scored **once**, in M7. Those results are reported as the independent result. Fixes made afterwards may be re-scored on the holdout, but those scores are labelled **"post-fix, no longer independent"**. |
| H-6 | **Proposed size [R]:** 2 projects; 12–18 documents in total (≥ 3 per Phase 1 file type); ≥ 40 planted items covering every MI, RV, CF and OBS rule, each rule with ≥ 2 positive instances where feasible; ≥ 3 clean negative-control documents. |

**Independence limitations (stated in every metric report):**
- the holdout author is an AI model of the same family as the developer, so blind spots may be correlated;
- the author uses the same fixture-generation libraries (reportlab, openpyxl), so file-production artefacts are similar;
- the author knows the fixture spec, so the holdout tests the *specified* variations, not unknown real-world ones;
- **synthetic results are not evidence of reliability on real project documents.** Real-world reliability needs licence-cleared public documents or approved company documents in a later phase.

### 15.3 Metric reporting rules
Every reported accuracy metric must state:
- the dataset (`dev` or `holdout`) and its seal hash;
- **numerator / denominator** (e.g. `27 / 30`), with no bare percentages;
- the number of projects, documents, pages and planted items in scope;
- the rule IDs covered;
- for detection metrics with a denominator below 30, the statement "small sample; not statistically meaningful as a general accuracy estimate";
- the fixed sentence: *"Measured on synthetic data generated for this project. Not evidence of reliability on real project documents."*

---

## 16. Acceptance criteria

### 16.1 Hard invariants — must hold on dev and holdout (results reported as numerator/denominator)

| ID | Invariant | How tested |
|---|---|---|
| INV-01 | Every factual claim cites file, document number + revision (when resolved), and page or sheet + cell; the resolver passes for all cited evidence | End-to-end CLI run; resolver report |
| INV-02 | Zero values in statements that are absent from cited evidence | V-03 over all claims |
| INV-03 | Every conflict has ≥ 2 sources and class UNKNOWN; zero silent resolutions | Report vs ground truth |
| INV-04 | Zero cross-project citations; a run on SYN-001 opens no SYN-002 path | File-access audit hook (`sys.addaudithook`) in the test |
| INV-05 | Zero network attempts (sockets blocked during the test run; static import check) | Test |
| INV-06 | Missing convention → dependent output is UNKNOWN or "not evaluated"; zero revision orders inferred without a basis | Manifest-ablation tests |
| INV-07 | Every input file appears in Coverage with a status | Test |
| INV-08 | Identical inputs → identical `report.json` (excluding `run_id` and timestamps) | Two runs, compared |
| INV-09 | Zero unescaped document-derived Markdown/HTML in `report.md` | Injection fixture |
| INV-10 | Execution responsibility is never inferred: a project with Piping documents but Piping absent from `contracted_scope` reports "not declared as contracted" and never "contracted" | Dedicated fixture |
| INV-11 | BOQ: item no / description / unit / quantity displayed text equals the source cell text exactly; zero pricing-column values in outputs; zero computed numbers in the BOQ section | Fixture with formulas, merged cells, rate/amount columns |
| INV-12 | Delivery model shown with the fixed responsibility statement; absent → UNKNOWN | Test |
| INV-13 | Section 6 contains only OBS-rule claims with ≥ 2-document evidence or scoped absence; zero forbidden phrases | V-07 + test |
| INV-14 | A hanging, crashing, oversized or zip-bomb file yields a Coverage status and the run completes for the other files | Fault fixtures |

### 16.2 Detection behaviour — compared with ground truth by semantic keys (document number, revision, page/cell, attribute), never by internal IDs

| ID | Behaviour | Dev | Holdout |
|---|---|---|---|
| DET-01 | Document identity (number, revision, title) | all correct | report n/N; ≥ 0.90 **[R]** |
| DET-02 | RV-01..05 | all detected | ≥ 0.90 **[R]** |
| DET-03 | MI-01..08 | all detected | ≥ 0.90 **[R]** |
| DET-04 | CF conflicts: recall / precision | all / all | recall reported; precision ≥ 0.95 **[R]** |
| DET-05 | OBS-01..07: each rule positive and negative instances | all correct | ≥ 0.90 **[R]** |
| DET-06 | False positives on negative controls | 0 | ≤ 1 per control set **[R]**, each explained |

Every holdout miss is recorded with its cause. Thresholds are **provisional** and require approval (P1-D-07).

---

## 17. Reuse of requirements from 02 (v0.1)

| 02 ID | Phase 1 use |
|---|---|
| FR-ARC-001/002 | Deterministic stages separated; values traceable (V-03) |
| 02 §3–§4 | Claim classes and tiers, unchanged |
| FR-INT-003 | User declarations (description, delivery model, contracted scope) as T3 |
| FR-DOC-001 (citation part), FR-DOC-002, FR-DOC-003, FR-DOC-004 | Revisions, conflicts, untrusted text |
| FR-EPI-001..003, FR-EVI-001..003 | Classification, citation |
| FR-VER-002, FR-VER-003 | Deterministic checks; failing claims removed or flagged |
| FR-MEM-004 | Project isolation (applied to runs and outputs) |
| FR-SAF-001 | No external writes |
| FR-SEC-001 | Classification labels; unlabelled → confidential |
| FR-ING-004, FR-ING-005 | Text documents with location metadata; read-only, idempotent processing |
| FR-DGM-001 | Drawing-derived *geometry* not used; title-block **text** is T2 text evidence, not topology |
| NFR-REL-001, NFR-REL-003, NFR-ARCH-001/002, NFR-SEC-002/003 | As written |
| **Not used in Phase 1** | FR-SEC-002 (no outbound path exists), NFR-PRV-\* (no provider), FR-MEM-001..003 (no sessions or case files; immutable run outputs instead) |

---

## 18. Assumptions and open questions

| ID | Assumption | Status |
|---|---|---|
| P1-A-01 | Default glossaries in Appendix B are generic engineering terms, not company conventions; the user reviews them in M0 | **[A]** needs approval |
| P1-A-02 | Users run Phase 1 locally from the CLI; no multi-user operation | **[A]** |
| P1-A-03 | Python ≥ 3.11 on Linux or macOS. `resource` limits are Linux/macOS only; Windows gets timeouts without memory limits | **[A]** |
| P1-A-04 | Drawings of interest have an accessible text layer; image-only drawings are reported, not read | **[A]** |

| ID | Open question |
|---|---|
| Q-P1-01 | Should a later phase use `delivery_model` to suggest which party normally provides a missing item? (Phase 1: no.) |
| Q-P1-02 | Which document and status vocabularies does the company actually use (CQ-04)? Phase 1 works without them, but OBS-06 and RV-03(c) need them declared. |
| Q-P1-03 | Should `.xls` and `.docx` be supported in a later increment of Phase 1? |
| Q-P1-04 | Who performs human spot-checks of citations at completion (Q-02)? |

---

## 19. Phase 1 completion criteria
1. All INV-01..14 hold on the dev set **and** the holdout (n/N reported).
2. DET thresholds met on the holdout, or each shortfall explained and accepted by the user.
3. Independent (Opus) review completed; high-severity findings fixed.
4. Human spot-check of ≥ 30 randomly sampled citations from the SYN-001 report (**[R]**), result recorded as n/N.
5. The user reviews the SYN-001 sample report and finds it usable.
6. README states CLI-prototype status, the operating requirements (§14.2) and the synthetic-validation limitation.
7. `CURRENT_STATE.md` updated; the session stops for approval.

---

## Appendix A — Banner applied to 01–03

> **Status note (Phase 1).** This document is v0.1 and was written for a maintenance-investigation direction. For Phase 1, `docs/spec/phase-1-document-intelligence.md` governs wherever the two conflict. Maintenance-specific items (D-02, D-03, UC-01–UC-06, FR-AST-\*, FR-PRC-\*, FR-MNT-\*, FR-INV-\*, EVD-001/002, A-02) are inactive pending the v0.2 rewrite. Cross-cutting requirements remain in force as listed in the Phase 1 specification §17.

## Appendix B — Default vocabularies (WALL-E defaults, **[A]**, for user review)

These are generic engineering vocabulary, not company conventions. The manifest may override or extend them in a later schema version.

**B.1 Placeholder markers (MI-03):** `TBD`, `TBA`, `TBC`, `HOLD`, `ON HOLD`, `BY OTHERS`, `LATER`, `TO BE CONFIRMED`, `TO BE ADVISED`, `?` *(only when it is the entire value of a field)*. Case-insensitive, whole-token match.

**B.2 Document reference patterns (MI-02, RV-04):** phrases "refer to", "see", "as per", "in accordance with", "reference drawing", "ref. dwg", followed by a token matching `document_number_pattern`. **If no `document_number_pattern` is declared, MI-02 and RV-04 are not evaluated** (Coverage says so).

**B.3 Scope headings (7.3):** "Scope", "Scope of Work", "Scope of Supply", "Work Included", "Work Excluded", "Exclusions", "Battery Limits", "Interfaces".

**B.4 BOQ headers (P1-BOQ-R6):** item: `Item`, `Item No`, `No.`, `Ref`, `S/N`; description: `Description`, `Item Description`; unit: `Unit`, `UoM`, `Unit of Measure`; quantity: `Qty`, `Quantity`. Pricing columns (identified to exclude them): `Rate`, `Unit Rate`, `Unit Price`, `Amount`, `Total`, `Price`.

**B.5 Attribute glossary (CF, OBS-05):**

| Canonical attribute | Accepted labels (case-insensitive) |
|---|---|
| design_pressure | Design Pressure, Des. Press., Design Press |
| operating_pressure | Operating Pressure, Op. Press., Working Pressure |
| test_pressure | Test Pressure, Hydrotest Pressure, Hydrostatic Test Pressure |
| design_temperature | Design Temperature, Des. Temp. |
| operating_temperature | Operating Temperature, Op. Temp. |
| material | Material, MOC, Material of Construction |
| flow_rate | Flow, Flow Rate, Rated Flow, Capacity *(pumps only, when the unit is volumetric)* |
| head | Head, Rated Head, Total Head, Differential Head |
| motor_power | Motor Rating, Motor Power, Rated Power |
| voltage | Voltage, Rated Voltage |
| frequency | Frequency |
| speed | Speed, Rated Speed |
| nominal_size | Size, Nominal Size, NPS, DN, Line Size |
| pressure_rating | Rating, Pressure Rating, Class, PN |

Qualifier words: design, operating, test, min, max, suction, discharge, inlet, outlet.

**B.6 Units and conversion (CF-05):**
- **Pressure:** barg, bara, kPa(g/a), MPa(g/a), psig, psia. `bar`, `kPa`, `MPa` and `psi` without g/a are **ambiguous → NOT_COMPARABLE**. Gauge and absolute are never compared with each other.
- **Temperature:** °C, °F, K.
- **Length:** mm, m, in.
- **Power:** kW, W. `hp` is ambiguous (several definitions) → NOT_COMPARABLE.
- **Voltage:** V, kV.
- **Frequency:** Hz.
- **Flow:** m³/h, L/s, L/min, US gpm. Plain `gpm` → NOT_COMPARABLE.
- **Speed:** rpm, min⁻¹.
- **Not converted:** nominal size (NPS ↔ DN is a designation mapping, not a unit conversion); materials and ratings (compared as normalised strings only).
- **Conversion factors:** exact defined constants, documented with their source in code.
- **Cross-unit tolerance [R]:** conflict if the relative difference exceeds **1%** after conversion. Same unit: exact compare.

**B.7 Standard designation patterns (OBS-01/02):** organisation prefix + identifier + optional edition/year, for the prefixes ISO, IEC, EN, BS, BS EN, ASME, API, ASTM, AWS, NFPA, DIN, NEMA, IEEE, CMAA, MSS SP. Example forms: `ASME B31.3-2022`, `IEC 60034-1:2017`, `AWS D1.1/D1.1M:2020`, `ISO 4427-2:2019`. Only the designation and edition are **matched and quoted**; WALL-E makes no claim about any standard's content.

**B.8 Forbidden phrases in section 6 (V-07):** adequate, inadequate, sufficient, insufficient, compliant, non-compliant, complies, approved (except when quoting a status field), acceptable, unacceptable, safe, unsafe, should, must, recommend, ensure, correct, incorrect, best practice.
