# HANDOFF — Next: M2 (Plan Mode — EnterPlanMode tool + per-turn attachment)

> Updated by: M1 autonomous agent
> Date: 2026-06-08

---

## 1. Current initiative

- **slug**: `plan-surface`
- **current milestone**: M1 ✓ (done 2026-06-08)
- **next milestone**: `M2` — Plan Mode — EnterPlanMode tool + per-turn attachment
- **all milestones (per PLAN)**: M1 [done], M2 [next], M3 [pending]

## 2. Completed milestones

### M1

- **commit**: see `[plan-srf/M1]` commit
- **files changed**: `todo.py` (new), `todo_tool.py` (new),
  `tests/test_todo.py` (new), `tests/test_repl_todo.py` (new),
  `models.py`, `context.py`, `loop.py`, `cli.py`, `metrics.py`,
  `trace.py`, `compact.py`, `provider.py`
- **tests added**: `tests/test_todo.py` (22 cases), `tests/test_repl_todo.py` (8 cases). Total: 835 → 864 (+29)
- **behavior implemented**: TodoWrite V1 (single-tool, in-memory). `todo_write`
  registered externally by `_build_repl_loop` via shared `_todos_list` closure.
  System prompt gains `_TODO_MANAGEMENT_SECTION` when `enable_todo_teaching=True`.
  Turn-based reminder via double-AND integer counters injected fresh each turn
  via `ContextBuilder.build(todo_nudge=TodoNudge(...))` kwarg — NOT permanently
  in transcript. `/todos` slash command. CLI flags: `--no-todo-reminder`,
  `--todo-reminder-turns N`.
- **design decisions (deviations from PLAN)**:
  - `Counter-based timing`: used simple `int` fields instead of transcript
    scanning. Gives exact per-turn firing at turn N. Visible in:
    `loop.py:_maybe_inject_todo_nudge`. Impact on M2: none.
  - `TodoNudge via build() kwarg not transcript append`: nudge injected
    fresh each turn (mirrors SnipNudge). Visible in: `context.py:_todo_nudge_dict`.
    Impact on M2: attachment ordering for PlanModeAttachment should follow
    the same pattern.
  - `External registration in _build_repl_loop`: AgentLoop checks
    `"todo_write" in registry._tools` to set `_todo_nudge_machinery_enabled`.
    Impact on M2: `enter_plan_mode` should also be registered externally
    in `_build_repl_loop` (or in `_register_tools` — per PLAN's note that
    TS always registers EnterPlanMode unconditionally).
- **known limitations**:
  - `shouldDefer=true` (TodoWriteTool.ts:51) not implemented.
  - verificationNudgeNeeded branch (TodoWriteTool.ts:76-86) skipped.

## 3. Current repo state

- **tests**: 864 passing
- **mypy**: clean (no issues found in 26 source files)
- **ruff**: clean (All checks passed!)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

- **TodoNudge injection pattern**: `_maybe_inject_todo_nudge()` returns
  `TodoNudge | None` which is passed to `build(todo_nudge=...)`. Do NOT
  append nudges to transcript — injection must be per-turn-fresh.
- **Loop registration pattern**: `AgentLoop` does NOT register `todo_write`.
  Checks `"todo_write" in registry._tools`. External registration is in
  `_build_repl_loop`. Preserve this pattern for M2's `enter_plan_mode`.

## 5. Next milestone guidance

For `M2` — Plan Mode — EnterPlanMode tool + per-turn attachment:

- **next scope**: see `initiatives/current/PLAN.md` M2 section and
  `initiatives/current/config.yaml` for authoritative scope.
  Key: `permission.py` (PermissionMode enum + PlanModeAttachment),
  `plan_mode_tools.py` (register_enter_plan_mode_tool),
  `tools.py` (Tool.read_only field + audit), `loop.py`
  (_permission_mode field, _set_permission_mode, soft-deny in _execute_one,
  plan_mode_attachment build() kwarg), `context.py` (plan_mode_attachment
  kwarg injection), `cli.py` (/plan slash command).
- **critical architecture**: TS does NOT filter tools at the schema layer
  in plan mode. Tool list is mode-invariant. Constraint enforced via
  (1) per-turn `<system-reminder>` attachment, (2) runtime soft-deny in
  _execute_one. Mirror this exactly.
- **relevant source files** (read BEFORE implementing):
  - `claude-code-source-code/src/utils/attachments.ts:1186` (getPlanModeAttachments)
  - `claude-code-source-code/src/tools/EnterPlanModeTool/EnterPlanModeTool.ts`
  - `claude-code-source-code/src/utils/permissions/permissions.ts:932`

The full ready-to-run prompt is at:
`initiatives/current/prompts/M2.md`
