# HANDOFF — Next: M3 (optional — see PLAN for scope)

> Updated by: `M2` session
> Date: 2026-05-25
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-demo`
- **current milestone**: just-completed `M2` — capture-real-api-artifacts-for-3-scenarios
- **next milestone**: `M3` — (see `initiatives/current/PLAN.md` for M3 scope)
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [pending]

## 2. Completed milestones

### M1

- **commit**: `(see git log)` `[ctx-demo/M1] --microcompact-minutes (both CLIs) + --max-turns (openai REPL)`
- **files changed**: `src/simple_coding_agent/compact.py`, `src/simple_coding_agent/cli.py`, `src/simple_coding_agent/openai_cli.py`, `tests/test_compact.py`, `tests/test_cli.py`, `tests/test_openai_cli_repl.py`
- **tests added**: `test_cli.py` (+1), `test_openai_cli_repl.py` (+2), `test_compact.py` (guard test updated, net 0 new). Total: 816 → 819 (+3)
- **behavior implemented**: Both `simple-agent --repl` and `simple-agent-openai --repl` now accept `--microcompact-minutes N`, which overrides `MicroCompactor.threshold_minutes` via the existing three-state precedence (explicit flag > `_AGGRESSIVE_THRESHOLDS` preset > built-in default of 60). `simple-agent-openai --repl` additionally accepts `--max-turns N`, which causes the REPL to exit cleanly (same path as `/exit`: dumps SessionMemory, returns 0) after exactly N user turns; slash commands do not count as turns. The turn counter lives in `cli._drive_repl_session` (shared by both REPLs). The `MicroCompactor` guard was relaxed from `threshold_minutes < 1` to `threshold_minutes < 0` so that `--microcompact-minutes 0` is valid ("any non-zero age qualifies").
- **design decisions (deviations from PLAN)**:
  - **Guard relaxed to N < 0**: PLAN offered "relax to N<0 OR set flag minimum to 1". Chose relaxation so `--microcompact-minutes 0` works exactly as PLAN described ("any age qualifies"). The guard test in `test_compact.py` was updated accordingly (now tests `threshold_minutes=-1`). Visible in: `compact.py:319`, `tests/test_compact.py:481`. Impact on M2: can use `--microcompact-minutes 0` in scenario 03 as originally specified.
  - **`resolved_microcompact_minutes` unified across aggressive/non-aggressive**: The aggressive branch previously hardcoded `microcompact_minutes` from the preset. Now both branches read `resolved_microcompact_minutes` (from `_resolve_threshold`), so an explicit `--microcompact-minutes` flag wins over the aggressive preset. Visible in: `cli.py:447–483`. Impact on M2: pass `--microcompact-minutes 0` alongside `--aggressive-thresholds` and 0 wins; omit it and the preset's 1 minute applies.
- **known limitations**:
  - (none)

### M2

- **commit**: `(see git log)` `[ctx-demo/M2] real-API artifact captures for snip+externalize, full compact, microcompact`
- **files changed**: `demo/_scripts/capture_scenario.py`, `demo/_artifacts/01_tool_result_management/{transcript.txt,trace.stderr,metrics.json,stats_output.txt}`, `demo/_artifacts/02_full_compact/{...}`, `demo/_artifacts/03_microcompact/{...}`
- **tests added**: 0 (M2 is a pure side-effect milestone)
- **behavior implemented**: Created `demo/_scripts/capture_scenario.py` (≤200 LOC SDK-based capture driver). Runs three scenarios against the DashScope API using `qwen3.6-plus`, writes 4 artifacts per scenario. All three exit gates pass.
- **design decisions (deviations from PLAN)**:
  - **Scenario 01 needs 3 reads, not 2**: `should_snip()` in `snip.py` uses `_PATH_THRESHOLD=3` (requires 3 reads of the same path before returning True). The PLAN assumed 2 reads would suffice. Added a 3rd "check for changes" read of `small.txt` so snip fires. See `snip.py:147`.
  - **`microcompact_minutes=60` for scenario 01**: The aggressive preset sets `microcompact_minutes=1`, but `qwen3.6-plus` in thinking mode takes ~60 seconds per API call. With the preset, microcompact would fire after the 2nd turn and clear tool results before snip could accumulate 3 reads. Explicitly passing `microcompact_minutes=60` (overrides the preset via three-state precedence) prevents this interference.
  - **`externalized_bytes` read from context builder**: `_build_repl_loop` creates `ToolResultStore(max_inline_chars=2000)` and passes it to `ContextBuilder`, but does NOT wire it to `AgentLoop`. Therefore `AgentLoop._tool_result_store = None` and `_refresh_externalized_bytes()` always returns 0. Trace confirms externalization DID happen (`[trace] [externalize] bytes=3800`). The driver reads `loop._context_builder._store.total_externalized_bytes` directly and patches the metrics dict before writing `metrics.json`. No `src/` changes were made.
- **known limitations**:
  - See Section 5 for the wiring bug.

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `(see git log)` — `git -C python-replica log --oneline -1`
- **tests**: 819 passing (unchanged from M1 — M2 adds no tests)
- **mypy**: clean (no issues in 26 source files)
- **ruff**: clean
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that M3 and subsequent milestones MUST respect. Update by
> ADDING — only remove a constraint by quoting it and explaining why it
> is retired.

- **do not modify**:
  - `MicroCompactor.__init__` guard: now accepts `threshold_minutes >= 0`; do not tighten back to `>= 1`. The guard test (`test_compact.py::test_microcompactor_rejects_negative_minutes`) pins this at -1.
- **preserve**:
  - `cli._drive_repl_session` signature now has `max_turns: int | None = None` (defaulting to None = unlimited). Both REPLs call it; do not remove this parameter.
  - Three-state precedence in `cli._resolve_threshold` covers `"microcompact_minutes"` with `preset_key="microcompact_minutes"`. Both REPLs share this path. Do not add a separate aggressive-branch local override for `microcompact_minutes`.
- **compatibility requirements**:
  - `--microcompact-minutes N` accepts N=0 (immediate) through any positive integer. Argparse type is `int`, no explicit lower bound in argparse (the guard in `compact.py` handles N<0 at construction time).
  - `--max-turns N` is openai_cli only; `simple-agent --repl` does not expose it (by design; MockProvider REPL has no artifacts to capture).

## 5. Known bugs / technical debt for M3+

### Bug: `_build_repl_loop` does not wire `tool_result_store` to `AgentLoop`

- **location**: `src/simple_coding_agent/cli.py` — the `_build_repl_loop` function's `loop_kwargs` dict (around line 505–523)
- **symptom**: `loop._metrics.externalized_bytes` is always 0 even when externalization DID occur (visible in `[trace] [externalize] bytes=N` events).
- **root cause**: `_build_repl_loop` creates `ToolResultStore(max_inline_chars=2000)` and passes it to `ContextBuilder(tool_result_store=...)`, but `loop_kwargs` does NOT include `tool_result_store`. Therefore `AgentLoop._tool_result_store = None`, and `AgentLoop._refresh_externalized_bytes()` (which reads `self._tool_result_store.total_externalized_bytes`) returns early with 0.
- **workaround (M2)**: Read the real value from `loop._context_builder._store.total_externalized_bytes`. This is the same store that `ContextBuilder` uses for externalization.
- **fix (M3+)**: Add `"tool_result_store": tool_result_store` to `loop_kwargs` in `_build_repl_loop`. This is a 1-line `src/` change; M2 was not allowed to make it.
