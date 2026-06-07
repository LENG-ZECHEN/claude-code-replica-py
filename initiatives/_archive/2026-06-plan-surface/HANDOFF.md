# HANDOFF — plan-surface initiative COMPLETE (M3 done)

> Updated by: M3 autonomous agent
> Date: 2026-06-08

---

## 1. Current initiative

- **slug**: `plan-surface`
- **current milestone**: M3 ✓ (done 2026-06-08) — FINAL MILESTONE
- **next milestone**: none — initiative complete
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done]

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
  - `External registration in _build_repl_loop`: AgentLoop checks
    `"todo_write" in registry._tools` to set `_todo_nudge_machinery_enabled`.
- **known limitations**:
  - `shouldDefer=true` (TodoWriteTool.ts:51) not implemented.
  - verificationNudgeNeeded branch (TodoWriteTool.ts:76-86) skipped.

### M2

- **commit**: see `[plan-srf/M2]` commit
- **files changed**: `permission.py` (new), `plan_mode_tools.py` (new),
  `tests/test_permission_mode.py` (new), `tests/test_enter_plan_mode.py` (new),
  `tests/test_plan_mode_soft_deny.py` (new), `tools.py`, `models.py`,
  `transcript.py`, `compact.py`, `context.py`, `metrics.py`, `trace.py`,
  `loop.py`, `snip_tool_model.py`, `todo_tool.py`, `tool_registry_factory.py`,
  `tests/test_agent_integration.py`
- **tests added**: 3 new test files (18 new cases). Total: 864 → 882 (+18)
- **behavior implemented**: `PermissionMode(StrEnum)` (NORMAL/PLAN),
  `PlanModeAttachment` (frozen dataclass opaque marker), `ENTER_PLAN_MODE_TEACHING_TEXT`,
  `register_enter_plan_mode_tool` with `read_only=True`, `Tool.read_only: bool = False`
  field (audit: `read_file/list_files/search_text/snip_history/enter_plan_mode/todo_write`
  all `read_only=True`), `ATTACHMENT_PLAN_MODE` message type, soft-deny in
  `_execute_one` (unknown tools also denied in plan mode), `_set_permission_mode`
  helper, `_maybe_arm_plan_mode_attachment` helper, `plan_mode_attachment=` kwarg
  in `ContextBuilder.build()`, 3 new metrics counters.
  Tools schema is mode-invariant (tools list never changes between NORMAL/PLAN).
- **design decisions**:
  - `enter_plan_mode registered in tool_registry_factory with no-op lambda`:
    `build_default_registry` registers it with `lambda _mode: None` so unit
    tests pass without a loop. `AgentLoop._register_tools()` re-registers with
    the real `_set_permission_mode` closure via overwrite (ToolRegistry.register
    silently replaces). Visible in: `tool_registry_factory.py`, `loop.py:_register_tools`.
  - `Unknown tools are denied in plan mode`: the soft-deny check catches
    `UnknownToolError` from `registry.get()` and treats unknown as non-read-only.
    This handles `write_memory_entry` (not in default registry since no
    project_memory) correctly. Visible in: `loop.py:_execute_one`.
  - `snip_history and todo_write read_only=True set at source`:
    Added directly in `snip_tool_model.py:register_snip_history_tool` and
    `todo_tool.py:register_todo_write_tool` — not as a post-registration patch.
  - `_set_permission_mode does NOT yet pass source= to tracer`:
    M3 prompt implies `source="slash"` vs `source="enter_plan_mode_tool"` was
    supposed to be wired in M2, but M2 tests don't check for it and M2 scope
    doesn't mention it. M3 must add `source` kwarg when wiring the `/plan`
    slash command.

### M3

- **commit**: see `[plan-srf/M3]` commit
- **files changed**: `plan_mode_tools.py`, `metrics.py`, `loop.py`, `cli.py`,
  `tool_registry_factory.py`, `tests/test_agent_integration.py`,
  `tests/test_enter_plan_mode.py` (ruff cleanup),
  `tests/test_plan_mode_soft_deny.py` (ruff cleanup),
  `tests/test_exit_plan_mode.py` (new), `tests/test_repl_plan_mode.py` (new)
- **tests added**: 17 new cases. Total: 882 → 899 (+17; gate was ≥10)
- **behavior implemented**:
  - `PlanRejectedError(RuntimeError)` in `plan_mode_tools.py` — mirrors
    `SnipRefusedError`; ToolExecutor converts it to `is_error=True`.
  - `register_exit_plan_mode_tool(registry, mode_setter, approval_callback)`
    factory with `read_only=True`, schema `{plan: str ≥1}`, approval path flips
    NORMAL and returns "Plan approved.", rejection raises `PlanRejectedError`.
  - `_confirm_exit_plan(plan_text) -> bool` in `cli.py` — blocks on
    `input("Approve plan? (y/N): ")`; EOFError/KeyboardInterrupt → False.
  - `/plan` slash command bidirectional toggle (NORMAL↔PLAN), no approval
    prompt, both directions emit `source="slash"` trace, transcript preserved.
  - `_set_permission_mode(mode, *, source="tool")` — added `source` kwarg,
    passes it to `tracer.emit("permission", ..., source=source)`.
  - `_exit_plan_mode_callback` no-op on loop — overwritten by `_build_repl_loop`
    with `_confirm_exit_plan` after `AgentLoop.__init__` runs.
  - `plan_mode_exits_approved` and `plan_mode_exits_rejected` counters added to
    `MetricsCollector`; `plan_mode_exits` converted to computed property (sum).
  - `exit_plan_mode` registered in `build_default_registry` (no-op defaults)
    and re-registered by `AgentLoop._register_tools()` + `_build_repl_loop`.
- **design decisions**:
  - `_exit_plan_mode_callback no-op on loop`: loop's own callback always
    returns False. `_build_repl_loop` overwrites via a second
    `register_exit_plan_mode_tool` call after AgentLoop init. This preserves
    the same "no-op in unit tests, real callback in CLI" pattern used by
    `enter_plan_mode`. Unit tests that build loops directly and want to test
    approval use `_build_repl_loop` (which wires `_confirm_exit_plan`) and
    monkeypatch `builtins.input`.
  - `M2 ruff cleanup bundled into M3`: M2 left 16 ruff errors (unused imports
    in test files). Fixed as part of M3 so the baseline is clean before
    committing. Impact: immaterial (test-only import removal).
  - `plan_mode_exits property`: `plan_mode_exits` is now a computed property
    `approved + rejected`. `record_plan_mode_exit()` (called by the slash
    toggle) increments `plan_mode_exits_approved` (manual exit treated as
    "approved" since user explicitly chose it).

## 3. Current repo state

- **tests**: 899 passing, 1 xpassed
- **mypy**: clean (no issues found in 30 source files)
- **ruff**: clean (All checks passed!)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

- **TodoNudge injection pattern**: `_maybe_inject_todo_nudge()` returns
  `TodoNudge | None` which is passed to `build(todo_nudge=...)`. Do NOT
  append nudges to transcript — injection must be per-turn-fresh.
- **Loop registration pattern**: `AgentLoop._register_tools()` re-registers
  `enter_plan_mode` AND `exit_plan_mode` with the real closures, overwriting
  the no-op lambdas from `build_default_registry`. `_build_repl_loop` then
  does a THIRD registration of `exit_plan_mode` to inject `_confirm_exit_plan`.
  Preserve this three-layer pattern if exit_plan_mode behavior ever changes.
- **Tools schema is mode-invariant**: `registry.to_api_format()` is called
  unconditionally regardless of `_permission_mode`. Do NOT filter tools by mode.
  The soft-deny in `_execute_one` is the ONLY enforcement mechanism at runtime.
- **`_set_permission_mode` now has `*, source: str = "tool"` kwarg**: backward
  compatible. Both `/plan` (source="slash") and tool-driven transitions (source
  defaults to "tool") emit the source in the permission trace. Do not remove.
- **read_only flag audit**: `read_file, list_files, search_text, snip_history,
  enter_plan_mode, todo_write, exit_plan_mode` are `read_only=True`. Any new
  read-only tool must also set `read_only=True` at registration time.
- **`plan_mode_exits` is a computed property**: not a stored field. Any code
  that tries to assign to `metrics.plan_mode_exits` will fail. Use
  `record_plan_mode_exit_approved()` or `record_plan_mode_exit_rejected()`.

## 5. Next milestone guidance

**This is the final milestone. The plan-surface initiative is complete.**

There is no M4. The review session (run by `run_all_milestones.sh`) will audit
this initiative, write `REVIEW.md`, and archive `initiatives/current/` into
`initiatives/_archive/`.

Deferred items (not in any future M — record for future initiatives if needed):
- Plan-content file persistence (TS `plans.ts writeFile + getPlanFilePath`).
- `allowedPrompts` schema (TS scoped-Bash permission requests in ExitPlanMode).
- Reentry attachment (TS `plan_mode_reentry` message kind sent after rejection).
- Analytics + teammate mailbox + autoMode integration.
- `_confirm_exit_plan` blocks the event loop in `--stream` mode (acceptable for
  the replica; documented in CLAUDE.md Current Limitations).
