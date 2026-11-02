# WALL-E — Project Instructions for Claude

## WALL-E Model and Agent Routing Policy

### Objective
Use the most cost-efficient Claude model and agent configuration that reliably satisfies each task's acceptance criteria.

### Model selection

* Opus: Complex architecture, high-impact design decisions, difficult debugging, security reviews, and independent critical reviews.
* Sonnet: Default implementation model for Python, tests, APIs, algorithms, and ordinary refactoring.
* Haiku: Simple, isolated, mechanical tasks, basic documentation, classification, and extraction.
* Fable: Escalation for exceptionally difficult reasoning or long-horizon tasks when Opus fails the required evaluation.

Always verify available model names and account access before selecting a model.

### Execution policy

1. Read only the project instructions and documents relevant to the assigned task.
2. Identify the task's complexity, risk, dependencies, and affected files.
3. Select the least expensive model likely to meet the quality requirements.
4. Escalate when the task is ambiguous, high-risk, cross-cutting, or the current model cannot resolve it.
5. Use specialist subagents only when their work is independent and has a clear deliverable.
6. Do not spawn unnecessary agents or duplicate analysis.
7. Never allow concurrent agents to modify the same files without an explicit coordination plan.

### Approval gates

1. Analyze the task.
2. Present the implementation plan, affected files, risks, and tests.
3. Wait for explicit approval.
4. Implement only the approved scope.
5. Run relevant tests and report actual results.
6. Request an independent review for significant changes.
7. Update CURRENT_STATE.md.
8. Stop and wait for approval before the next task or phase.

### Token efficiency

* Avoid repeating project context already stored in repository documentation.
* Do not dump entire files or the entire repository unless necessary.
* Prefer concise summaries and focused diffs.
* Run targeted tests first, followed by broader regression tests when appropriate.
* Never omit important tests merely to save tokens.
* Never sacrifice correctness, evidence, or security for lower token usage.

### Reporting
Every task report must include:

* What changed.
* Why it changed.
* Files affected.
* Tests actually executed.
* Passed, failed, skipped, and untested cases.
* Remaining risks and limitations.
* Decisions requiring user approval.

The model must never claim success without verification.

---

## Model availability (reference — re-verify every session)

Snapshot as of 2026-11-02, from the Claude Code environment (not an account-access test):

| Tier   | Model ID            | Subagent `model` value |
|--------|---------------------|------------------------|
| Fable  | `claude-fable-5-1`  | `fable`                |
| Opus   | `claude-opus-5-5`   | `opus`                 |
| Sonnet | `claude-sonnet-5-5` | `sonnet`               |
| Haiku  | `claude-haiku-5-5`  | `haiku`                |

These names are exposed by the environment; actual account access to each model has not been confirmed by a live call. Model availability changes — verify before relying on this table.

The approval gates above are behavioral guidance only; they are not enforced by tooling (hooks/permissions).
