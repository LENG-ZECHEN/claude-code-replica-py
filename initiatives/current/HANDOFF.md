# HANDOFF — Next: M3 (real-api-visibility-demo-and-guard)

> Updated by: M2 (manual exit-ritual collation — agent session was
> terminated by API usage exhaustion before reaching §5; source work was
> complete, this collation closes the bookkeeping)
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `observable-thresholds`
- **current milestone**: _(none in flight — M2 just landed)_
- **next milestone**: `M3` — real-api-visibility-demo-and-guard
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [next]

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
  - `MicroCompactor.__init__` now requires a `super().__init__()` call from subclasses, because the tracer attribute is set in the parent. This forced a 1-line addition (`super().__init__()`) in three files that subclass `MicroCompactor` outside the package: `examples/microcompact_demo.py:55`, `tests/test_loop.py:147`, `tests/test_microcompact_runtime.py:103`. Impact on next milestone: M3 must NOT remove this `super()` chain, and any new subclass of a Tracer-bearing component MUST call `super().__init__(tracer=...)`.
- **known limitations**:
  - The §2 exit-gate smoke run drove only one trivial REPL turn (`hello`/`/exit`), which proves `[trace] [budget]` and `[trace] [memory_select]` fire on a normal turn and the silent-default path. It does NOT exercise the rarer channels (`compact` / `snip` / `externalize` / `reactive` / `auto_learn`); those are unit-tested individually in `tests/test_trace.py` (channel-name coverage test) and exercised end-to-end by M2.
  - This commit was produced by manual exit-ritual collation, NOT by the autonomous agent. The agent ran 243 tool-use turns, made all required Edits / Writes, and stopped at a successful Edit on `tests/test_trace.py` (transcript line 1721/1727). Claude Code v2.1.148's auto-compaction thrash-loop protection (v2.1.89+) terminated the session cleanly with exit code 0 before the model could `end_turn` and run §5.

### M2

- **commit**: `14299af` `[obs-thr/M2] add --aggressive-thresholds preset + SnipTool/MicroCompactor constructor params`
- **files changed**:
  - modified: `src/simple_coding_agent/cli.py` (added `_AGGRESSIVE_THRESHOLDS` module-level dict, `_format_aggressive_banner()`, `--aggressive-thresholds` argparse flag, banner emission in `_build_repl_loop`, preset wiring into all constructors)
  - modified: `src/simple_coding_agent/compact.py` (`MicroCompactor.__init__` now accepts `threshold_minutes: int = 60` constructor param; `should_microcompact` uses `self._threshold_minutes` as default, overridable per-call)
  - modified: `src/simple_coding_agent/openai_cli.py` (added `--aggressive-thresholds` flag, wired into `_run_openai_repl`)
  - modified: `src/simple_coding_agent/snip.py` (`SnipTool.__init__` now accepts `keep_recent: int = 3` constructor param; internal algorithm uses `self._keep_recent`)
  - new: `examples/aggressive_thresholds_demo.py` (~114 LoC, MockProvider-based, 8-turn scripted run with repeated read_file calls; shows full_compacts=1, snip_runs=6)
  - modified: `tests/test_snip.py`, `tests/test_repl.py` (+4 cases), `tests/test_openai_cli_repl.py` (+2 cases)
  - new: `tests/test_aggressive_thresholds_demo.py`
- **tests added**: Total 542 → 551 (+9)
- **behavior implemented**: Module-level `_AGGRESSIVE_THRESHOLDS` dict in `cli.py` (8 keys: `compact_threshold=0.2`, `keep_recent=2`, `microcompact_minutes=1`, `max_inline_chars=2000`, `total_budget_chars=8000`, `snip_keep_recent=1`, `context_tokens=4000`, `reserved_output_tokens=512`). When `--aggressive-thresholds` is passed, `_build_repl_loop` constructs all components with these values. Precedence rule: explicit `--max-context-tokens` / `--reserved-output-tokens` / `--max-steps` override the preset for that field only. Banner printed once at REPL start on stdout: `[aggressive-thresholds] compact=0.2, microcompact=1min, inline=2k, total=8k, snip_keep=1, ctx=4k, out=512`.
- **known limitations**:
  - Agent session terminated by API usage exhaustion before reaching §5 exit ritual. Source work verified complete by manual audit (pytest 551, mypy clean, ruff clean, banner smoke test, demo run). This commit is the manual exit-ritual collation per RUNBOOK recovery path.
  - The 8-turn REPL smoke test with `--verbose --aggressive-thresholds` producing `[trace] [compact]` + `[trace] [snip]` on stderr was verified via the demo script (`full_compacts=1, snip_runs=6`), not via the literal CLI pipe invocation in §5, because MockProvider's default scripted responses don't generate tool calls. The demo's `_build_repl_loop(aggressive_thresholds=True)` call path is identical to the CLI's.

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `TBD` `[obs-thr/M2] add --aggressive-thresholds preset + SnipTool/MicroCompactor constructor params`
- **tests**: 551 passing
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
  - `_AGGRESSIVE_THRESHOLDS` module-level dict in `cli.py` (8 keys: `compact_threshold`, `keep_recent`, `microcompact_minutes`, `max_inline_chars`, `total_budget_chars`, `snip_keep_recent`, `context_tokens`, `reserved_output_tokens`). M3's `visibility_full_demo.py` imports this dict by name. The key set is frozen — do not add, rename, or remove keys.
- **preserve**:
  - Constructor default pattern: every Tracer-injected component uses `tracer: Tracer | None = None` with `self._tracer = tracer or NullTracer()` so old call sites keep working at zero overhead.
  - `auto_learn.detect_cue(text, tracer: Tracer | None = None) -> str | None` signature — both `cli.py` and `openai_cli.py` callers pass the active REPL tracer.
  - `super().__init__()` chain in `MicroCompactor` subclasses (see M1 design decision above).
  - `SnipTool(keep_recent: int = 3)` default — M3 must NOT change this default.
  - `MicroCompactor(threshold_minutes: int = 60)` default — M3 must NOT change this default.
- **compatibility requirements**:
  - **Secret-leak invariant**: trace lines MUST NOT contain raw user input or LLM output text. Only metadata (counts, token estimates, entry names, scores, tool ids). Enforced by `tests/test_trace.py::test_stderr_tracer_no_raw_user_input_through_repl`. Any new fire site MUST honor this.
  - Fire-site ordering: perform-action → `tracer.emit(...)` → `metrics.record_*()` (where applicable).

## 5. Next milestone guidance

For `M3` — real-api-visibility-demo-and-guard:

- **next scope (refined from PLAN by M2 experience)**:
  - New `examples/visibility_full_demo.py` (~120-160 LoC): real-API demo using `OpenAIProvider` (or any OpenAI-compatible endpoint), runs with `--aggressive-thresholds` wiring, drives 8 turns with repeated `read_file` calls, saves 4 artifacts to a timestamped `artifacts/<run-id>/` directory: `trace.stderr`, `metrics.json`, `summary.md`, `transcript.json`. Guard: `--confirm-api-call` flag required to make any real API call (exit code 2 if missing). Exit code 3 if at least one of compact/snip channels never fires.
  - Update `.gitignore` to exclude `artifacts/` in the same M3 commit.
  - New `tests/test_visibility_full_demo.py` (~6 cases): use `_ExplodingProvider` (raises `PromptTooLongError`) to trigger reactive-compact path without a real API key; assert artifact directory is created, `trace.stderr` contains expected `[trace]` prefixes, `metrics.json` is valid JSON with the 6 MetricsCollector fields, `summary.md` contains one row per active channel, exit code 3 fires when no compact/snip.
  - README.md "Examples" section: document `visibility_full_demo.py` usage.
  - Mark `initiatives/current/PLAN.md` STATUS=complete (M3 is the last milestone — see M3 prompt §5.5).
- **channels confirmed firing under aggressive thresholds** (M2 demo, `snip_keep=1`, `compact_threshold=0.2`, `ctx=4k`, 8-turn repeated-read): `snip` (6×), `compact` (1×), `microcompact` (1×). M3's `summary.md` must emit all 9 channel rows (0 is a valid count; row omission is not).
- **relevant files**: `examples/visibility_full_demo.py` (new), `.gitignore` (update), `tests/test_visibility_full_demo.py` (new), `README.md` (update Examples section), `initiatives/current/PLAN.md` (mark STATUS=complete in §5.5)
- **risks**:
  - **Real-API cost**: `--confirm-api-call` gate is mandatory; without it the demo must NOT make any network call.
  - **Artifact directory must be in `.gitignore` in the same commit**.
  - **Exit codes 2 and 3 must be distinct**: exit 2 = guard missing, exit 3 = no compact/snip fired.
  - **`super().__init__()` chain** — any new subclass of a Tracer-bearing component must call `super().__init__()`.
  - **`_AGGRESSIVE_THRESHOLDS` import**: `from simple_coding_agent.cli import _AGGRESSIVE_THRESHOLDS` (module-level, not a function scope).

The full ready-to-run prompt is at:
`initiatives/current/prompts/M3.md`
