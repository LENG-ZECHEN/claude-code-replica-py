# plan-surface progress log

Cumulative milestone log for the `plan-surface` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[plan-srf/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

## M1 — done 2026-06-08

- **files changed**: `todo.py` (new), `todo_tool.py` (new),
  `tests/test_todo.py` (new), `tests/test_repl_todo.py` (new),
  `models.py`, `context.py`, `loop.py`, `cli.py`, `metrics.py`,
  `trace.py`, `compact.py`, `provider.py`
- **tests**: 835 → 864 (+29; gate was ≥14)
- **behavior implemented**: TodoWrite V1 (single-tool, in-memory, no
  persistence). `todo_write` JSON-schema tool registered externally by
  `_build_repl_loop` via shared `_todos_list` closure. System prompt
  gains `_TODO_MANAGEMENT_SECTION` when `enable_todo_teaching=True`.
  Turn-based reminder fires via strict double-AND integer counters:
  `turns_since_write >= N AND turns_since_reminder >= N` (default N=10);
  result is a fresh `TodoNudge` passed to `ContextBuilder.build()` as
  a kwarg each turn (not appended to transcript). Counter reset on
  `todo_write` success in `_execute_one`. `/todos` slash command shows
  glyph-prefixed list. CLI flags: `--no-todo-reminder`, `--todo-reminder-turns N`.
- **design decisions (deviations from PLAN)**:
  - `Counter-based timing instead of transcript scanning`: PLAN implied
    scanning message history à la TS `getTodoReminderTurnCounts`. Using
    simple `int` fields on the loop gives exact per-turn firing at turn N
    without off-by-one edge cases from assistant-message counting.
    Visible in: `loop.py:_maybe_inject_todo_nudge`. Impact on M2: none.
  - `TodoNudge via build() kwarg not transcript append`: nudge is
    injected fresh each turn through `ContextBuilder.build(todo_nudge=)`
    (mirrors the SnipNudge pattern) rather than permanently in transcript.
    Visible in: `context.py:_todo_nudge_dict`, `loop.py:_maybe_inject_todo_nudge`.
    Impact on M2: transcript remains clean; cooldown works correctly.
  - `External registration in _build_repl_loop`: AgentLoop does NOT
    auto-register `todo_write`; it only checks `"todo_write" in registry._tools`
    to set `_todo_nudge_machinery_enabled`. Keeps quiescent path clean.
- **known limitations**:
  - `shouldDefer=true` (TodoWriteTool.ts:51) not implemented — no
    ToolSearch in replica, tool is always in initial schema.
  - verificationNudgeNeeded branch (TodoWriteTool.ts:76-86) skipped —
    GrowthBook-gated in TS, no verification agent in this replica.

## M2 — done 2026-06-08

- commit: [plan-srf/M2] (see git log)
- tests: 864 → 882 (+18; gate was ≥14)
- mypy: clean | ruff: clean
- files changed: `permission.py` (new), `plan_mode_tools.py` (new),
  `tests/test_permission_mode.py` (new), `tests/test_enter_plan_mode.py` (new),
  `tests/test_plan_mode_soft_deny.py` (new), `tools.py`, `models.py`,
  `transcript.py`, `compact.py`, `context.py`, `metrics.py`, `trace.py`,
  `loop.py`, `snip_tool_model.py`, `todo_tool.py`, `tool_registry_factory.py`,
  `tests/test_agent_integration.py`
- exit gate: 3 new test files pass, pytest ≥14 growth, tools schema
  mode-invariant (deep-equal), ATTACHMENT_PLAN_MODE in turn 2 messages,
  soft-deny fires for write_file/run_shell/write_memory_entry in plan mode,
  read_file/todo_write allowed → PASS (18 new tests pass, all 882 green)
- notes: `_set_permission_mode` does NOT yet pass `source=` to tracer;
  M3 must add that parameter when wiring the `/plan` slash command.
