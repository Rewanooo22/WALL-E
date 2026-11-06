# WALL-E — Current State

_Last updated: 2026-11-06_

## Product (confirmed)
WALL-E is an internal, evidence-grounded, multi-discipline engineering and project execution assistant. Initial scope: document intelligence across Mechanical, Piping, Fabrication, Installation, and E&I. Read-only and advisory; no engineering approvals.

## Current phase
**Status (2026-11-06):** the M1 review fixes from all five rounds are committed together in the commit following `90be243` on `claude/hopeful-tesla-10yahv`, and pushed to PR #3. **PR #3 is not merged** (the merge needs user approval; GitHub PR/CI state not independently verified). The "uncommitted" notes below describe the state during each round.

**Phase 1 — Multi-discipline Document Intelligence.** M0 approved and committed (`fd3816c`, merged via PR #2). **M1 committed (`191b5d6`, head `90be243`) on branch `claude/hopeful-tesla-10yahv`, PR #3, not merged** (verified via git: not in `origin/main`; GitHub PR/CI state not independently verified). An independent Opus review of `90be243` (2026-11-04) found F1–F13; **fixes F1–F7 approved and implemented in the working tree, uncommitted.** A second independent review (2026-11-05) passed F1–F7 and raised M-1, L-1..L-6, I-1..I-5, T1–T6, S-1; M-1, L-2..L-5, T1, T3, T6, S-1 were approved and implemented (uncommitted). A third independent review (2026-11-05) found that the M-1 fix itself was flawed (N-1, see below) and raised N-2..N-7; N-1 (file-identity matching), N-2, N-3, N-4, N-7 were approved and implemented (uncommitted, 2026-11-06). A fourth independent review (2026-11-06) raised F-1..F-5; F-1, F-2, F-3 (path-specific classification) and the tie-break test were approved and implemented (uncommitted, 2026-11-06). A fifth independent review raised F-A..F-E; **F-A and F-C approved and implemented (uncommitted, 2026-11-06), awaiting independent review and user review.** F8–F13, L-1, L-6/F-B (before M3), I-1..I-5, N-5, F-4, F-5, F-E deferred (see Known risks). The earlier M1 completion review's G1 (unreadable file aborts the scan) is covered by F2; G2–G9 are not recorded in the repository and have not been reconciled.

## Governing documents
- `docs/spec/phase-1-document-intelligence.md`: governs Phase 1 (approved).
- `docs/adr/ADR-001-phase1-deterministic-baseline.md`: accepted. Deterministic CLI pipeline; no LLM, network, agent framework, vector search or database.
- `docs/spec/01–03` v0.1: carry a Phase 1 precedence banner. Maintenance-specific items are inactive; cross-cutting requirements remain in force (Phase 1 spec §17). A v0.2 rewrite is planned after Phase 1.

## Completed
- `CLAUDE.md` routing policy (`c082477`).
- Specs 01–03 v0.1 draft checkpoint (`cd38a21`).
- Product redirection analysis (project execution focus).
- M0: Phase 1 spec, ADR-001, banners on 01–03 (`fd3816c`).
- M1 (`191b5d6`, PR #3): `pyproject.toml`, `.gitignore`, `src/wall_e/{models,project,run}.py`; tests for manifest, discovery, models, run manifest, static network policy. As committed: 45 tests reported passing in the cloud session (4 of 4 deliberate mutations caught; not re-verified); on Windows: 44 passed, 1 skipped (symlink test).
- M1 review fixes F1–F7 (uncommitted, 2026-11-04): resolved-path containment (symlinks, NTFS junctions, reparse points → `REJECTED_PATH`, never traversed or hashed); filesystem errors → `UNREADABLE` with error class only, scan continues, unlistable directories recorded, unlistable root fatal; `run_id` validated and resolved run dir must stay under `out_root`, outside and not an ancestor of the project; `project_id`/`schema_version` must be JSON strings; UTF-8 BOM accepted; `project_id` validated with `fullmatch` (trailing newline and other suffixes rejected); unlistable project root is a fatal error, never an empty Coverage. At the 121-test stage: 121 passed, 3 skipped on Windows; **51** of those test cases failed against the unfixed `90be243` code (corrected from "44", which was the count at the earlier 95-test stage).
- Second-round fixes (uncommitted, 2026-11-05):
  - Classification (rule B): `classification` key missing → manifest default (§4.2); explicit invalid value (incl. null) → confidential (`fail_safe_invalid_label`) with an issue; duplicate declarations → most restrictive.
  - M-1 (superseded by N-1, below): a per-character uppercase key approximated NTFS case-insensitivity. The review found it wrong in both directions (N-1); it has been removed.
  - Contracted scope (rule C): `declared_by` must be exactly `"user"` (missing/other → not declared); `disciplines` missing/null/non-list → not declared; any invalid entry in a non-empty list → not declared, issue lists the invalid entries; `[]` → declared with zero.
  - L-2: run directory refused if its resolved path differs from the literal path (link/junction under `out_root`). L-3: Windows reserved device names refused for `project_id`/`run_id` path components; mkdir errors and a created path that is not a real directory → `OutputDirError`. L-4: unreadable `project.json` → `ManifestError` with error class only. L-5: a directory vanishing after listing → `UNREADABLE`; a dangling link/junction stays `REJECTED_PATH`.
  - Tests: T1 (directory resolve failure, RuntimeError), T3 (access recorder also records directory listings), T6 (symlink helper skips only on missing privilege, WinError 1314 / EPERM); Windows `icacls` deny tests for a file, a directory and `project.json`. Correction: as written in this round, the `icacls` helper denied `(F)` and ignored the restore's exit code; on pytest temp folders the restore failed silently and every Windows run left files that pytest could not delete (one cleanup warning per run). Fixed in round 3 (N-2).
  - Results on Windows: 169 passed, 3 skipped (2 need symlink privilege, 1 POSIX-only), 1 warning (the N-2 cleanup failure). 30/30 targeted mutations caught: **run by the implementer only; the reviewer did not reproduce this** (re-running would have left more undeletable folders). Against the unfixed `90be243` code the suite then gave 84 failed, 14 errors (fixtures patching names absent in old code), 71 passed, 3 skipped (the reviewer reproduced these figures).
- Third-round fixes (uncommitted, 2026-11-06):
  - N-1 (Medium): the M-1 key over-merged names NTFS keeps distinct (e.g. `kalıp.pdf` / `KALIP.pdf`: the unlisted `KALIP.pdf` inherited `synthetic`; the same in case-sensitive directories) and under-merged names NTFS treats as one file (e.g. Greek `ᾀ` / `ᾈ`), so it could lower classifications. Replaced by file-identity matching. Manifest entries match by exact path first. Otherwise the entry path is looked up with `lstat` (metadata only, nothing is read), and the entry applies to every discovered entry with the same `(st_dev, st_ino)`, including hard-link aliases (superseded by F-3 in round 4: classifications are now path-specific). Several entries for one file take the most restrictive classification. No case folding is done anywhere. Lookups go only through directories the scan traversed (matched by identity), so never through links, junctions, rejected or unlisted directories. On Windows, names with `:` or a device name (CON, NUL, COM1…) are not looked up. A match by identity and a merge of several entries are each reported as manifest issues.
  - Fallback where identity is unavailable (`st_ino == 0`, lookup refused, or lookup error): only exact path matching applies. An entry that does not match exactly is reported as "listed file not found …" with the reason, and is not applied: the file it may name keeps the manifest default. That is never silent, but a stricter declaration made under another spelling is not applied in this case.
  - N-2: the `icacls` helper denies only `(RD)`. A failed restore, or a path still unreadable afterwards, fails the test.
  - N-3: the access recorder compares literal and resolved locations, so an access through a junction/symlink to an outside target is recorded. A sanity test proves it. The INV-04 sibling-project test now uses it.
  - N-4: the run directory checks compare path strings exactly (Path equality ignores case on Windows), so projects `test-1` and `TEST-1` cannot share an output directory.
  - N-7: test for the post-creation check (the created directory resolving elsewhere, or to a case variant).
  - Side effect of removing the case key: N-6 resolved (manifest entries are now sorted by exact path on every platform).
  - Results on Windows (2026-11-06): **181 passed, 3 skipped** (same 3 as before), no warnings; the run's temp folder had 0 entries with a DENY ACE and deleted cleanly. Against the pre-round code (rebuilt from the session record): 15 of the new tests fail (reproduced by the reviewer). 7 of those are the N-1/N-4 bugs themselves (kalıp ×2, fsutil case-sensitive folder, Greek pair, three N-4 output tests including the case-exact post-creation check). The rest exercise new behaviour, or names absent from the old code.
  - Mutations (implementer run, 2026-11-06, not yet reproduced by a reviewer): 42 mutations, each with its own pytest temp folder checked for DENY entries and deleted before the next (0 DENY entries, all deleted); the control run on unmutated code passed. 39/42 reported caught. One survivor (`F3-no-ancestor`) was a harness artifact: its temp folder name contained "ancestor", which satisfied the test's message regex. Re-run under a neutral name it is caught, so **40/42**. Genuine survivors: removing the `S_ISDIR` check in identity lookups (redundant: a link's identity is never a traversed directory's) and the tie-break that picks the exact-path entry's `classification_source` when classifications are equal (now tested, round 4).
- Fourth-round fixes (uncommitted, 2026-11-06), after the round-3 review (FIX BEFORE MERGE):
  - F-1 (Low–Medium): Win32 strips trailing dots/spaces, so `os.lstat` on `a.pdf.` (a distinct file, creatable via `\\?\`) returned the identity of `a.pdf`, and it inherited `a.pdf`'s declaration. All metadata lookups for matching (discovered entries, traversed directories, declared paths) now use Windows extended-length (`\\?\`) paths. NTFS-level behaviour is unchanged: case-insensitivity, `fsutil` case-sensitive directories, 8.3 short names. `a.pdf.`, `a.pdf ` and device-name spellings are taken literally. Reports keep the discovered relative paths.
  - F-2: `NUL ` and `CON .pdf` were added to the device-name test, which checks that they are never looked up (no `lstat`) and never opened.
  - F-3 (user decision): classifications are path-specific.
    - An entry applies to exactly one discovered path: the exact path, or, for another spelling, the entry the filesystem resolves it to (same parent directory and file identity).
    - When several hard-link names in that directory are the same file, the exact on-disk name from the Windows final-path query decides. If it cannot be determined, the entry is not applied and an issue says so.
    - Classifications are never transferred between hard-link names. An undeclared name keeps `default_classification`.
    - Names of one file that end up classified differently are reported as an issue.
  - Tie-break (documented in `_apply_declarations`): when several entries apply to one path, the most restrictive classification wins. Among equally restrictive entries, the exact-path entry supplies `classification_source`; otherwise the first in manifest path order (Unicode code-point order) does. Tested in both manifest orders.
  - Results on Windows: **192 passed, 3 skipped** (same 3), no warnings. The 30 targeted tests ran and none skipped. The test temp folders had 0 DENY entries and no leftover trailing-dot/space names, and deleted cleanly.
  - Mutations (implementer run, 2026-11-06): 19 targeted at N-1/N-3/F-1/F-2/F-3/tie-break; the control run passed. Every temp folder had 0 DENY entries and was deleted. **17/19 caught.** Survivors, both untested defensive checks: the `S_ISDIR` check in lookups (redundant, see round 3), and the link/reparse-point check before the on-disk-name query in `_on_disk_rel` (reached only when several same-directory hard-link names of one file are themselves links).

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
- Deferred M1 review findings: F8 runtime socket block in tests and wider static import check (M3); F9 reproducibility (no source commit in run manifest, no lock file for transitive deps, CRLF on Windows, write race); F10 manifest read before size check; F11 PDF header offset / encrypted XLSX status (M3); F12 model-level validation gaps (M6); F13 non-string notes dropped silently.
- Hard links to files outside the project cannot be detected by path resolution. Hard links inside the project keep path-specific classifications (F-3); names of one file classified differently are reported.
- N-1 residual (Low, open): where the filesystem reports no file identity (`st_ino == 0`), declarations match exact paths only; a declaration under another spelling is reported as not found and not applied (see the fallback above). Declarations under spellings NTFS resolves to the same entry (case variants, 8.3 short names) apply to that entry; trailing-dot/space spellings are taken literally (F-1). Outside Windows (no on-disk-name query) a non-exact spelling of a file with several names (hard links) is never applied, with an issue (F-A). The same holds on Windows for spellings of links/reparse points with several names. If such an entry was stricter than the default, the file keeps the lower default; the user chose this (never transfer between paths).
- Deferred fourth-review items: F-4 (Info): identity collisions on filesystems with non-unique inode numbers (some SMB/FUSE) could mismatch an entry (an issue is raised); a check-then-use window between the directory identity check and the next lookup (same class as L-1); concurrent `test-1`/`TEST-1` runs can leave an empty refused run directory. F-5 (Info): the `nxt.parent != cur` check in `_resolve_declared` is unreachable (harmless); entries for `project.json` or a directory are reported as "not found …".
- Deferred second-review items (status: open, accepted for now):
  - L-1 (Low): check-then-use window: a directory swapped for a junction after its containment check is listed by `os.walk`; outside names can reach Coverage (as `REJECTED_PATH`), nothing outside is opened or hashed. Acceptable under §14.2 (trusted sources).
  - L-6 (Low): Windows names with a trailing dot (creatable via `\\?\`) are misreported (e.g. `a.pdf.` as a duplicate of `a.pdf`, content not hashed).
  - I-1 (Info, speculative): resolving a directory symlink to a UNC path could touch the network; OneDrive cloud placeholders untested.
  - I-2 (Info): an internal link to `project.json` gets `duplicate_of="project.json"`, which is not in Coverage.
  - I-3 (Info): manifest entries for files inside unlistable/rejected directories are reported "listed file not found".
  - I-4 (Info): a walk error without a filename is treated as a fatal root error (fails closed).
  - I-5 (Info): content duplicates keep their own label; a synthetic primary can stand for confidential-labelled copies.
- Deferred third-review items:
  - N-5 (Info, open): the root manifest is excluded from Coverage by an exact-case name comparison. On Windows a manifest saved as `Project.json` is loaded and also listed as an input file.
  - N-6 (Info): resolved as a side effect of N-1 (no platform-dependent sort key remains).
  - (Correction: an earlier version of this file said the M-1 case key "can only make a label stricter". That was false; see N-1.)
- Remaining test gaps: symlink and symlink-loop tests skip on Windows without symlink privilege; the chmod test is POSIX-only; no Python 3.11 interpreter available locally (3.11 compatibility checked by reading only); Linux CI has not run the fixed suite (on Linux the NTFS-specific N-1 tests and the case-insensitive-filesystem tests skip; the simulated, `fsutil`/case-sensitive-directory and hard-link tests run); T5: several new tests are guards that also pass on the unfixed code (e.g. one of the two N-7 tests pins an existing check).
- Local Windows environment differs from pins (pydantic 2.13.4, pytest 9.1.1, reportlab 4.4.2); `pdfplumber`, `pdfminer.six` and `pypdfium2` are not installed.

## Next step
The independent review of round 4 (2026-11-06) returned FIX BEFORE MERGE.
- Verdicts: F-1, F-2, tie-break and Scope PASS; F-3 PARTIAL.
- Full suite: 192 passed, 3 skipped (reproduced by the reviewer).
- Open findings:
  - F-A (Medium-Low, reproduced; fixed in round 5): a non-exact spelling with a single candidate is applied without confirming which name it refers to. Entry `PROJECT.JSON: synthetic` with `project.json` hard-linked to `a.pdf` lowers the undeclared `a.pdf` to synthetic, and the issue text is false. This violates the F-3 rule.
  - F-B (Low, the deferred L-6, measured): content and status checks still use Win32 paths, so `a.pdf.` is reported as a duplicate of `a.pdf`, and a directory named `sub.` is `UNREADABLE`. Classification is not affected. Fix before M3 workers open files.
  - F-C (Low): exact-path duplicate entries with equal classification keep the first entry's `classification_source` in manifest order (fixed in round 5).
  - F-E (Low): test gaps: UNC root, a case-variant hard-link test naming the second link, the `pytest.fail` in `finally` masking an exception.
  - Decision: the ambiguity rule does not apply a stricter entry, so the named file keeps a lower default (with an issue).
- F-D (stale `_parse_files` docstring) corrected after the review.

User decisions (2026-11-06): fix F-A and F-C; keep the ambiguity rule (never transfer a classification between paths); defer F-B until before M3; defer F-E.

Fifth-round fixes (uncommitted, 2026-11-06):
- F-A: a non-exact spelling is applied to a discovered path only once it is confirmed to name that very path. On Windows its exact on-disk name must equal the path. Where no on-disk name is available (other platforms, links), it must be the only candidate and the file's only name (link count 1). Otherwise the entry is not applied and an issue says so. On Windows, when the manifest also has a discovered hard-link name, a spelling that names the manifest is reported as naming it. Otherwise such an entry gets the generic "not a discovered file" or "could not be confirmed" issue. Reviewer probe P3 now gives `a.pdf` confidential / `built_in_default`.
- F-C: duplicate entries for one path with the same classification keep a `classification_source` chosen by fixed rank: explicit label > fail-safe for an invalid label > default. The result no longer depends on manifest order.
- Results on Windows: **206 passed, 3 skipped** (same 3), no warnings. 45 targeted tests passed. The test temp folders had 0 DENY entries and no trailing-dot/space names, and deleted cleanly. Mutations (implementer run): 6/6 caught; the control run passed and cleanup was clean after every run.

Independent review of round 5 (2026-11-06): F-A PASS, F-C PASS, Scope PASS; Docs PARTIAL (the manifest-message wording above, now corrected). Recommendation: MERGE. Full suite reproduced: 206 passed, 3 skipped. All 7 reviewer mutations were caught, including a full revert of F-A. Deferred (Low/Info):
- R5-2: with 3 or more conflicting duplicates, intermediate "conflicting duplicate" issues name the winner so far, not the final classification (pre-existing; the final result is correct).
- R5-3: a manifest stored as `Project.json` is discovered as an input (same as N-5).
- R5-4: a race between `lstat` and `realpath` in `_on_disk_rel` (same class as L-1; metadata only).
- R5-6: the link/reparse check in `_on_disk_rel` has no real-filesystem test (no symlink privilege here).

Final review of the full diff against `90be243` (2026-11-06): no blocking issue. Committed and pushed to PR #3. Next: the user's merge decision for PR #3. Next after merge: **M2**: fixture spec, then the blind holdout **before** any parser code or dev ground truth, then the dev fixture generator.
