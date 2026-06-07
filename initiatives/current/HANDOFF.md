# HANDOFF — Next: M1 (TodoWrite (V1) tool + teaching prompt + turn-based reminder)

> Updated by: Phase 1 bootstrap of `plan-surface`
> Date: 2026-06-08
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `plan-surface`
- **current milestone**: _(not started)_
- **next milestone**: `M1` — TodoWrite (V1) tool + teaching prompt + turn-based reminder
- **all milestones (per PLAN)**: M1 [next], M2 [pending], M3 [pending]

## 2. Completed milestones

_(none yet — this initiative has not started)_

<!--
After each milestone, the milestone agent APPENDS one subsection like:

### {{MILESTONE_ID}}

- **commit**: `<sha>` `[<commit_prefix>/{{MILESTONE_ID}}] <subject>`
- **files changed**: `<file1>`, `<file2>`, ...
- **tests added**: `<test_file>` (+N cases). Total: <before> -> <after>
- **behavior implemented**: <one-paragraph factual summary — what now
  works that did not before. Cite new public symbols / CLI flags /
  slash commands.>
- **design decisions (deviations from PLAN)**:
  - `<short title>`: <what was different and WHY>. Visible in:
    `<path:line>`. Impact on next milestone: <e.g., "must respect new
    invariant X">.
  - (none) if truly no divergences
- **known limitations**:
  - <thing not fully done; e.g., "happy-path only, error case deferred">
  - (none) if you fully cleaned up

Prior subsections are NEVER deleted or rewritten — each milestone is the
source of truth on itself.
-->

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `17e616dc7feeb563019ec3ba1b0fbd421b21554e` — `git -C python-replica show 17e616d`
- **tests**: 835 passing
- **mypy**: clean (no issues found in 26 source files)
- **ruff**: clean (All checks passed!)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: _(none yet — first milestone has free hand within its scope)_
- **preserve**: _(none yet)_
- **compatibility requirements**: _(none yet)_

## 5. Next milestone guidance

For `M1` — TodoWrite (V1) tool + teaching prompt + turn-based reminder:

- **next scope**: see `initiatives/current/PLAN.md` and
  `initiatives/current/config.yaml` for the authoritative scope.
  Replicate Claude Code's V1 TodoWrite (the single-tool, in-memory form
  enabled by `!isTodoV2Enabled()`) — explicitly NOT the V2 Tasks 6-tool
  suite. Three load-bearing pieces: tool body, teaching `## Todo
  Management` prompt section, turn-based reminder (strict double-AND
  via a single `TODO_REMINDER_TURNS=10` constant). Plus a fourth
  attachment type `ATTACHMENT_TODO_NUDGE` that shares the existing
  per-turn USER `<system-reminder>` injection path with SnipNudge /
  recall_hooks attachments.
- **relevant files**: M1 starts on a clean baseline. Per PLAN's
  Expected-files list:
  NEW: `src/simple_coding_agent/todo.py`, `src/simple_coding_agent/todo_tool.py`
  MODIFIED: `loop.py`, `context.py`, `tool_registry_factory.py`,
  `cli.py`, `openai_cli.py`, `models.py`, `transcript.py`,
  `compact.py`, `trace.py`, `metrics.py`
  TESTS: `tests/test_todo.py` (new), `tests/test_repl_todo.py` (new),
  `tests/test_trace.py` (extend negative-case coverage for new channel)
- **expected tests**: ≥ 14 new cases across `tests/test_todo.py` +
  `tests/test_repl_todo.py`. The CORE 10-turn cycle test (turn 10
  injects, turns 11-19 cooldown, turn 20 re-injects) is the unique
  signal that the strict V1 double-AND counter logic is correct.
- **risks**: see PLAN.md "Risks / known unknowns". Most relevant for
  M1: (a) attachment ordering when SnipNudge + TodoNudge arm in the
  same turn (already partly covered by `_coalesce_same_role`);
  (b) schema-strict providers and `"minLength": 1` encoding on the
  `content` / `activeForm` fields.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M1.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
