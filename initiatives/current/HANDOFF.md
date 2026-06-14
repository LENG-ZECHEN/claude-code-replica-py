# HANDOFF — Next: M1 (Generic ForkedAgentRunner)

> Updated by: Phase 1 bootstrap of `session-memory-dream`
> Date: 2026-06-15
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `session-memory-dream`
- **current milestone**: _(not started)_
- **next milestone**: `M1` — Generic ForkedAgentRunner (extract from ExtractMemoriesRunner)
- **all milestones (per PLAN)**: M1 [next], M2 [pending], M3 [pending], M4 [pending], M5 [pending], M6 [pending], M7 [pending]

## 2. Completed milestones

_(none yet — this initiative has not started)_

<!--
After each milestone, the milestone agent APPENDS one subsection like:

### M{N}

- **commit**: `<sha>` `[sm-dream/M{N}] <subject>`
- **files changed**: `<file1>`, `<file2>`, ...
- **tests added**: `<test_file>` (+N cases). Total: <before> -> <after>
- **behavior implemented**: <one-paragraph factual summary>
- **design decisions (deviations from PLAN)**:
  - `<short title>`: <what was different and WHY>. Visible in: `<path:line>`.
  - (none) if truly no divergences
- **known limitations**:
  - <thing not fully done>
  - (none) if you fully cleaned up

Prior subsections are NEVER deleted or rewritten — each milestone is the
source of truth on itself.
-->

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `094cf90d09fef37b3f8357b4e2b8de0434834dfd` — `git -C python-replica show 094cf90`
- **tests**: 912 passing (+1 xpassed)
- **mypy**: clean (`mypy src` → no issues in 30 source files)
- **ruff**: clean (`ruff check .` → All checks passed!)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: _(none yet — first milestone has free hand within its scope)_
- **preserve**: the 11-name trace channel vocabulary in `trace.py` is
  FROZEN and test-pinned — do NOT add a new channel (SM-compact reuses
  `compact`; dream surfaces via metrics + CLI, not a new channel).
- **compatibility requirements**: `session_store.py` JSON envelope changes
  must be backward-compatible (new keys optional; absent → empty/default),
  mirroring how `restored_files`/`timestamp` are already optional.

## 5. Next milestone guidance

For `M1` — Generic ForkedAgentRunner (extract from ExtractMemoriesRunner):

- **next scope**: see `initiatives/current/PLAN.md` and
  `initiatives/current/config.yaml` for the authoritative scope. M1
  generalizes the existing `ExtractMemoriesRunner` (extract_memories.py)
  into a reusable `forked_agent.py::ForkedAgentRunner` with a per-call
  `can_use_tool` gate + `context_messages` injection + configurable
  `max_turns`; `ExtractMemoriesRunner` becomes a thin wrapper. PURE
  refactor — existing extraction behavior must not change.
- **relevant files**: `src/simple_coding_agent/extract_memories.py`
  (source to generalize), new `src/simple_coding_agent/forked_agent.py`,
  `src/simple_coding_agent/tools.py` (ToolExecutor / ToolRegistry),
  `src/simple_coding_agent/permission.py` + `loop.py::_execute_one` (the
  soft-deny pattern the gate mirrors).
- **expected tests**: new `tests/test_forked_agent.py`; keep
  `tests/test_extract_memories*.py` green.
- **risks**: the real bug to fix — `extract_memories.py:118` stores
  `base_messages` but `run()` never sends them; ForkedAgentRunner must
  actually inject `context_messages` into the sub-agent's first call.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M1.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
