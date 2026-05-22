# HANDOFF — Next: M2 (aggressive-thresholds-preset)

> Updated by: M1 (manual exit-ritual collation — agent session was
> terminated by Claude Code thrash-loop protection at turn 243 before
> reaching §5; source work was complete, this collation closes the
> bookkeeping)
> Date: 2026-05-22
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `observable-thresholds`
- **current milestone**: _(none in flight — M1 just landed)_
- **next milestone**: `M2` — aggressive-thresholds-preset
- **all milestones (per PLAN)**: M1 [done], M2 [next], M3 [pending]

## 2. Completed milestones

### M1

- **commit**: `a052056` `[obs-thr/M1] wire Tracer Protocol + --verbose flag across context/memory pipeline`
- **files changed**:
  - new: `src/simple_coding_agent/trace.py`, `tests/test_trace.py`
  - wired Tracer into 10 src modules: `auto_learn.py`, `claude_md.py`, `cli.py`, `compact.py` (MicroCompactor + ContextCompactor), `context.py`, `loop.py`, `memory.py`, `openai_cli.py`, `snip.py`, `tool_result_store.py`
  - `super().__init__()` fixes in 3 inherited test helpers / demos: `examples/microcompact_demo.py`, `tests/test_loop.py`, `tests/test_microcompact_runtime.py`
  - new test cases in: `tests/test_cli.py` (+3), `tests/test_openai_cli_repl.py` (+2), `tests/test_repl.py` (+4)
- **tests added**: `tests/test_trace.py` (+13 cases). Other test files: +9. Total: 520 → 542 (+22)
- **behavior implemented**: `trace.py` exports a `Tracer` Protocol with two production implementations: `NullTracer` (default, `emit` body is `pass`, zero overhead) and `StderrTracer` (writes `[trace] [<channel>] k1=v1 k2=v2\n` per event, keys sorted for determinism). Eight components (`AgentLoop`, `ContextBuilder`, `ToolResultStore`, `ProjectMemory`, `ClaudeMdLoader`, `MicroCompactor`, `ContextCompactor`, `SnipTool`) accept `tracer: Tracer | None = None` and default to `NullTracer()` so existing call sites are unchanged. The pure-function `auto_learn.detect_cue` was extended to `detect_cue(text, tracer=None)`. All 9 documented channels emit at their fire sites: `compact` (`compact.py:442,472`), `reactive` (`loop.py:251,400`), `microcompact` (`compact.py:351`), `snip` (`snip.py:124`), `externalize` (`tool_result_store.py:150`), `memory_select` (`memory.py:355`), `claude_md` (`claude_md.py:45,72`), `auto_learn` (`auto_learn.py:52`), `budget` (`context.py:227`). A new `--verbose` argparse flag in `cli.py` and `openai_cli.py` picks `StderrTracer()` in `_build_repl_loop` / `_run_openai_repl`; default REPL path uses `NullTracer()`.
- **design decisions (deviations from PLAN)**:
  - `MicroCompactor.__init__` now requires a `super().__init__()` call from subclasses, because the tracer attribute is set in the parent. This forced a 1-line addition (`super().__init__()`) in three files that subclass `MicroCompactor` outside the package: `examples/microcompact_demo.py:55`, `tests/test_loop.py:147`, `tests/test_microcompact_runtime.py:103`. Impact on next milestone: M2 must NOT remove this `super()` chain, and any new subclass of a Tracer-bearing component MUST call `super().__init__(tracer=...)`.
- **known limitations**:
  - The §2 exit-gate smoke run drove only one trivial REPL turn (`hello`/`/exit`), which proves `[trace] [budget]` and `[trace] [memory_select]` fire on a normal turn and the silent-default path. It does NOT exercise the rarer channels (`compact` / `snip` / `externalize` / `reactive` / `auto_learn`); those are unit-tested individually in `tests/test_trace.py` (channel-name coverage test) and will be exercised end-to-end by M2 (aggressive-thresholds-preset) and M3 (visibility_full_demo).
  - This commit was produced by manual exit-ritual collation, NOT by the autonomous agent. The agent ran 243 tool-use turns, made all required Edits / Writes, and stopped at a successful Edit on `tests/test_trace.py` (transcript line 1721/1727). Claude Code v2.1.148's auto-compaction thrash-loop protection (v2.1.89+) terminated the session cleanly with exit code 0 before the model could `end_turn` and run §5. See [anthropics/claude-code#41796](https://github.com/anthropics/claude-code/issues/41796) for the protection mechanism.

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `a052056` `[obs-thr/M1] wire Tracer Protocol + --verbose flag across context/memory pipeline`
- **tests**: 542 passing
- **mypy**: clean (no issues found in 21 source files)
- **ruff**: clean (all checks passed)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**:
  - `Tracer` Protocol surface (`emit(channel: str, **fields) -> None`) — adding methods breaks `NullTracer`/`StderrTracer` and any external implementation.
  - `StderrTracer` output line format: `[trace] [<channel>] k1=v1 k2=v2\n` with keys sorted by `sorted(fields.keys())`. M3's `visibility_full_demo.py` will grep this format from the persisted `trace.stderr`.
  - The 9 channel names: `compact`, `reactive`, `microcompact`, `snip`, `externalize`, `memory_select`, `claude_md`, `auto_learn`, `budget`. These match `MetricsCollector` counter names where they overlap; adding or renaming is a coordination cost across docs + tests + the M3 summary.md generator.
- **preserve**:
  - Constructor default pattern: every Tracer-injected component uses `tracer: Tracer | None = None` with `self._tracer = tracer or NullTracer()` so old call sites keep working at zero overhead.
  - `auto_learn.detect_cue(text, tracer: Tracer | None = None) -> str | None` signature — both `cli.py` and `openai_cli.py` callers pass the active REPL tracer; downstream code may depend on this.
  - `super().__init__()` chain in `MicroCompactor` subclasses (see M1 design decision above).
- **compatibility requirements**:
  - **Secret-leak invariant**: trace lines MUST NOT contain raw user input or LLM output text. Only metadata (counts, token estimates, entry names, scores, tool ids). Enforced by `tests/test_trace.py::test_stderr_tracer_no_raw_user_input_through_repl` which feeds `sk-AAAA1234SECRET` through the REPL and asserts the secret is absent from stderr while `[trace]` lines are present. Any new fire site MUST honor this — never stringify user content into trace fields.
  - Fire-site ordering at every mechanism: perform-action → `tracer.emit(...)` → `metrics.record_*()` (where applicable). This keeps the event stream and post-hoc counter stream consistent.

## 5. Next milestone guidance

For `M2` — aggressive-thresholds-preset:

- **next scope (refined from PLAN by M1 experience)**:
  - Add module-level `_AGGRESSIVE_THRESHOLDS` dict in `cli.py` (8 keys: `compact_threshold`, `keep_recent`, `microcompact_minutes`, `max_inline_chars`, `total_budget_chars`, `snip_keep_recent`, `context_tokens`, `reserved_output_tokens`).
  - Refactor `SnipTool` to expose `keep_recent: int = 3` as a constructor parameter (default keeps current behavior byte-equivalent). Do this **first**, as its own test-first cycle; verify `tests/test_snip.py` is still green at default before adding the `keep_recent=1` case.
  - Add `--aggressive-thresholds` argparse flag to `cli.py` and `openai_cli.py`. Wire into `_build_repl_loop` (cli.py) and `_run_openai_repl` (openai_cli.py).
  - Precedence rule: explicit `--max-context-tokens` / `--reserved-output-tokens` / `--max-steps` override preset values for that field; unspecified fields take the preset. Test explicitly.
  - Banner printed once at REPL start (stdout, not stderr) when preset active; prefix `[aggressive-thresholds]`.
  - New `examples/aggressive_thresholds_demo.py` (~80 LoC, MockProvider).
- **relevant files**: `src/simple_coding_agent/snip.py`, `src/simple_coding_agent/cli.py`, `src/simple_coding_agent/openai_cli.py`, `examples/aggressive_thresholds_demo.py` (new), `tests/test_snip.py` (+1-2 cases), `tests/test_repl.py` (+3 cases), `tests/test_openai_cli_repl.py` (+2 cases). Target pytest >= 545.
- **expected tests**:
  - `tests/test_snip.py`: 1-2 new cases for `keep_recent=1`; existing cases must remain green at default.
  - `tests/test_repl.py` / `tests/test_openai_cli_repl.py`: flag wiring, banner emission, precedence rule (explicit flags win).
  - End-to-end exit-gate sanity: with `--verbose --aggressive-thresholds`, an 8-turn REPL with repeated `read_file` calls produces at least one `[trace] [compact]` and one `[trace] [snip]` on stderr; without `--aggressive-thresholds` the same input produces zero of each.
- **risks**:
  - **Don't trigger Claude Code thrash-loop protection again** — M2's scope is much smaller than M1 (mostly cli.py + snip.py refactor) so should complete in ≤ 50 tool turns. If you find yourself reading more than 5-6 large files, stop and split.
  - **`super().__init__()` chain** — if you add any new Tracer-bearing class, ensure subclasses call super. The MicroCompactor pattern is the worked example.
  - **Banner channel** — banner goes to stdout (not stderr) so it doesn't pollute the trace stream. Existing `[trace]` capture in tests must not see the banner.
  - **`_AGGRESSIVE_THRESHOLDS` is M3's import surface** — M3's `visibility_full_demo.py` imports it. Don't make the dict name private to a function; module-level is required.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M2.md`
