# HANDOFF — Next: M2 (capture-real-api-artifacts-for-3-scenarios)

> Updated by: `M1` session
> Date: 2026-05-25
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-demo`
- **current milestone**: just-completed `M1` — cli-flags-microcompact-minutes-and-max-turns
- **next milestone**: `M2` — capture-real-api-artifacts-for-3-scenarios
- **all milestones (per PLAN)**: M1 [done], M2 [next], M3 [pending]

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

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `(see git log)` — `git -C python-replica log --oneline -1`
- **tests**: 819 passing (was 816 before M1, delta +3)
- **mypy**: clean (no issues in 26 source files)
- **ruff**: clean
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that M2 and subsequent milestones MUST respect. Update by
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

## 5. Next milestone guidance

For `M2` — capture-real-api-artifacts-for-3-scenarios:

- **next scope**: Pure side-effect milestone. Run three scenarios against the real DashScope API (via `python-replica/.env`) and write artifacts under `demo/_artifacts/{01_tool_result_management,02_full_compact,03_microcompact}/`. Each scenario needs four files: `transcript.txt`, `trace.stderr`, `metrics.json`, `stats_output.txt` (first line `# model: <SIMPLE_AGENT_MODEL>`). Use an SDK-based capture driver (not shell-pipe stdin scripting) under `demo/_scripts/`, mirroring `examples/visibility_full_demo.py`. The `--microcompact-minutes 0` flag from M1 makes scenario 03 instantaneous.
- **relevant files**:
  - `examples/visibility_full_demo.py` — structural reference; reuse `_parse_trace_events` and `_new_run_dir` patterns
  - `python-replica/.env` — pre-configured with `DASHSCOPE_API_KEY`, `OPENAI_BASE_URL`, `SIMPLE_AGENT_MODEL`; do NOT create env.sample
  - `src/simple_coding_agent/openai_cli.py` — the CLI that M2 drives; now has `--max-turns` and `--microcompact-minutes` from M1
  - `demo/` — empty directory reserved for this initiative; M2 populates `demo/_scripts/` and `demo/_artifacts/`
- **expected tests**: M2 is a pure side-effect milestone (real-API artifact capture). No new tests.
- **risks**:
  - **`--microcompact-minutes 0` behavior**: The guard was relaxed to accept 0; `should_microcompact` fires when `current_time - latest_assistant_time > timedelta(minutes=0)`, i.e., any non-zero age. In practice this fires on the very next turn since processing takes >0ms. If for any reason the second turn's assistant timestamp equals the current time exactly (clock skew edge case), microcompact will NOT fire. Use a brief `time.sleep(0.01)` between turns in the capture driver if this proves flaky (unlikely in real API calls which take seconds).
  - **Model quota exhaustion**: See PLAN M2 notes for the swappable-model playbook (5 alternatives via the same `OPENAI_BASE_URL`). If two consecutive alternates fail with quota errors, STOP and surface to the owner.
  - **Per-scenario cost cap**: $0.10 per scenario, $0.20 total. Stop and report if exceeded rather than retrying.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M2.md`
