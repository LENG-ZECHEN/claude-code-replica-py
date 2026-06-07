# HANDOFF — Next: M3 (ExitPlanMode tool + CLI approval + bidirectional /plan toggle)

> Updated by: M2 autonomous agent
> Date: 2026-06-08

---

## 1. Current initiative

- **slug**: `plan-surface`
- **current milestone**: M2 ✓ (done 2026-06-08)
- **next milestone**: `M3` — ExitPlanMode tool + CLI approval + bidirectional /plan toggle
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [next]

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

## 3. Current repo state

- **tests**: 882 passing
- **mypy**: clean (no issues found in 28 source files)
- **ruff**: clean (All checks passed!)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

- **TodoNudge injection pattern**: `_maybe_inject_todo_nudge()` returns
  `TodoNudge | None` which is passed to `build(todo_nudge=...)`. Do NOT
  append nudges to transcript — injection must be per-turn-fresh.
- **Loop registration pattern**: `AgentLoop._register_tools()` re-registers
  `enter_plan_mode` with the real `_set_permission_mode` closure, overwriting
  the no-op lambda from `build_default_registry`. Preserve this pattern for
  M3's `exit_plan_mode`.
- **Tools schema is mode-invariant**: `registry.to_api_format()` is called
  unconditionally regardless of `_permission_mode`. Do NOT filter tools by mode.
  The soft-deny in `_execute_one` is the ONLY enforcement mechanism at runtime.
- **`_set_permission_mode` is a public method** (no leading `__`): M3's
  `/plan` slash command calls it directly via `loop._set_permission_mode(...)`.
  Do not rename or make it private.
- **read_only flag audit**: `read_file, list_files, search_text, snip_history,
  enter_plan_mode, todo_write` are `read_only=True`. Any new read-only tool
  must also set `read_only=True` at registration time.

## 5. Next milestone guidance

For `M3` — ExitPlanMode tool + CLI approval + bidirectional /plan toggle:

- **next scope**: `plan_mode_tools.py` gains `PlanRejectedError` and
  `register_exit_plan_mode_tool(registry, mode_setter, approval_callback)`.
  `cli.py` gains `/plan` bidirectional toggle slash command and
  `_confirm_exit_plan` helper. `tool_registry_factory.py` registers
  `exit_plan_mode`. `metrics.py` gains `plan_mode_exits_approved` and
  `plan_mode_exits_rejected` (the existing `plan_mode_exits` becomes the sum).
- **key architecture for M3**:
  - `exit_plan_mode` tool has `read_only=True` (the tool itself is read-only;
    the side-effect is mode flip on approval).
  - `approval_callback(plan_text: str) -> bool` — wired in `_build_repl_loop`
    as `_confirm_exit_plan`. MockProvider tests use a monkeypatched `input()`.
  - `/plan` slash command calls `loop._set_permission_mode(PermissionMode.PLAN)`
    or `loop._set_permission_mode(PermissionMode.NORMAL)` directly — NO approval
    prompt for the manual toggle (only tool-triggered exit needs approval).
  - **`source` kwarg for tracer**: M3 needs to add `source=` parameter to
    `_set_permission_mode` so `/plan` emits `source="slash"` vs the tool
    emitting `source="enter_plan_mode_tool"` / `source="exit_plan_mode_tool"`.
    The M3 test `test_repl_plan_mode.py` checks for this.
  - Transcript history is preserved across ALL mode transitions — the model
    keeps its `read_file`/`search_text` context after `/plan` exit.
- **files to read before implementing**:
  - `src/simple_coding_agent/plan_mode_tools.py` (M2 pattern to extend)
  - `src/simple_coding_agent/cli.py` (slash command registration pattern)
  - `src/simple_coding_agent/loop.py` (`_set_permission_mode`, `_permission_mode`)
  - `src/simple_coding_agent/snip_tool_model.py` (`SnipRefusedError` pattern for `PlanRejectedError`)
- **expected new test files**: `tests/test_exit_plan_mode.py`,
  `tests/test_repl_plan_mode.py` (≥10 cases total)
- **risks**:
  - The `input()` call in `_confirm_exit_plan` will block non-TTY environments.
    Tests must monkeypatch `builtins.input` — not `cli.input`.
  - `_set_permission_mode` currently has signature `(mode: PermissionMode) -> None`.
    Adding `source: str = "tool"` as a kwarg-only parameter is backward-compatible
    and the safe approach.
  - `plan_mode_exits` in M2 is `plan_mode_exits: int = 0` with
    `record_plan_mode_exit()`. M3 replaces/supplements with
    `plan_mode_exits_approved` and `plan_mode_exits_rejected`. Decide whether
    to keep or remove `plan_mode_exits` — the M3 prompt says "M2 generic
    plan_mode_exits is the SUM (computed as approved+rejected, not stored
    separately)" suggesting it should become a property not a field.
