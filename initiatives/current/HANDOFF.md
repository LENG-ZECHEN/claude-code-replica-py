# HANDOFF — Initiative complete (M3 was the last milestone)

> Updated by: `M3` session
> Date: 2026-05-22
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `observable-thresholds`
- **current milestone**: just-completed `M3` — real-api-visibility-demo-and-guard
- **next milestone**: _(none — initiative complete; PLAN.md marked `STATUS: complete`)_
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done]

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

### M3

- **commit**: `TBD` `[obs-thr/M3] visibility_full_demo.py + artifact guard + .gitignore`
- **files changed**:
  - new: `examples/visibility_full_demo.py` (~270 LoC; runs `OpenAIProvider` under `_build_repl_loop(aggressive_thresholds=True)`, drives 3 scripted turns, writes `transcript.txt` / `trace.stderr` / `metrics.json` / `summary.md` to `examples/_artifacts/visibility-demo-<UTC-timestamp>/` — operator overrides the parent via `--output-root`)
  - new: `tests/test_visibility_full_demo.py` (+6 cases — missing-confirm-flag exit 2, missing-API-key exit 3, four artifacts non-empty, `[trace] [budget]` + `[trace] [externalize]` lines present, summary.md row-per-channel, `.gitignore` guard)
  - modified: `.gitignore` (adds `examples/_artifacts/` so per-run artifact directories never enter version control; required by the same-commit invariant in M3 prompt §4)
  - modified: `README.md` (one new row in the `examples/` listing pointing operators at `visibility_full_demo.py`)
  - modified: `initiatives/current/PLAN.md` (added `> STATUS: complete (M1 + M2 + M3 shipped 2026-05-22)` between the provenance line and the `# Goal` heading)
  - modified: `initiatives/current/HANDOFF.md` (this file)
  - modified: `initiatives/current/PROGRESS.md` (appended `## M3 — done 2026-05-22` block; M1 and M2 blocks preserved verbatim)
- **tests added**: `tests/test_visibility_full_demo.py` (+6 cases). Total: 551 → 557 (+6)
- **behavior implemented**: `examples/visibility_full_demo.py` exposes an operator-facing demo that exercises every public observability surface introduced by M1 and M2 end-to-end against a real OpenAI-compatible endpoint. Argparse exposes three flags: `--confirm-api-call` (required; missing → print explanation, exit 2 — `OpenAIProvider` is **not** constructed on this path), `--model` (defaults to `$SIMPLE_AGENT_MODEL` or `gpt-4o-mini`), and `--output-root` (defaults to `examples/_artifacts/`; tests redirect to `tmp_path`). API-key check (`OPENAI_API_KEY` or `DASHSCOPE_API_KEY`) gates the happy path; missing → exit 3 with a stderr explanation, still without constructing a provider. The happy path opens `<run_dir>/trace.stderr` for write, wires `StderrTracer(stream=...)`, builds the loop via `cli._build_repl_loop(..., provider=OpenAIProvider(...), tracer=tracer, aggressive_thresholds=True)`, drives three scripted user turns (read `seed.txt`, read it again, leave a Chinese/English preference cue), then writes `transcript.txt` (human-readable rendering of `Transcript.to_jsonable(include_virtual=True)`), `metrics.json` (the six `MetricsCollector` fields), and `summary.md` (one row per locked channel + tokens-per-turn + counter dump). Channels are parsed back out of `trace.stderr` so the summary's "first fire site" column is grounded in real on-disk evidence.
- **design decisions (deviations from PLAN)**:
  - **`--output-root` flag was added beyond the PLAN sketch.** PLAN.md fixed the artifact root at `examples/_artifacts/`; the test surface needs the directory to be redirectable so unit tests do not write inside the repo. The flag defaults to `examples/_artifacts/` so the operator-facing behavior matches PLAN exactly. Visible in: `examples/visibility_full_demo.py:_build_parser`. Impact on later work: none — initiative is complete.
  - **Exit-code-3 semantics follow the M3 prompt, not the M2 HANDOFF.** The M2 HANDOFF §5 suggested exit 3 should mean "no compact/snip fired"; the M3 prompt explicitly redefined exit 3 as "missing API key" (and test case (b) in the prompt is built around that). Per the prompt's §3 rule that HANDOFF is advisory and the prompt is source of truth, exit 3 = missing API key. The "did compact/snip actually fire" signal lives in `summary.md` instead.
- **known limitations**:
  - The real-API code path (`_run`) is only smoke-verified through the CLI exit codes (`exit=2` for missing flag, `exit=3` for missing key); the artifact-writing branch is exercised by tests via a `MockProvider`-backed shim that replaces `OpenAIProvider`. A real-key end-to-end run is left to the operator (see M3 prompt §5 step 1 note that this is optional for the gate).
  - The summary's "first fire site" column shows the field values from the first event of each channel; if a future channel emits events whose first occurrence is uninformative, the operator may want a "best" or "representative" event instead. Defer to a future initiative.

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `TBD` `[obs-thr/M3] visibility_full_demo.py + artifact guard + .gitignore`
- **tests**: 557 passing (was 551 after `M2`, delta +6)
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

New constraints from M3:

- **do not modify**:
  - The four artifact filenames written by `visibility_full_demo.py`: `transcript.txt`, `trace.stderr`, `metrics.json`, `summary.md`. The M3 prompt's exit gate names them exactly; any future demo that wants to add more artifacts must NOT rename these four.
  - `.gitignore` entry `examples/_artifacts/` — committing anything under that directory dirties the working tree and breaks the autonomous-loop pre-flight check.
- **preserve**:
  - The two exit codes — `2` (missing `--confirm-api-call`) and `3` (missing API key) — and the invariant that neither path constructs `OpenAIProvider`. The `_ExplodingProvider` tripwire in `tests/test_visibility_full_demo.py` enforces this.

## 5. Next milestone guidance

**This was the last milestone.** PLAN.md is marked `STATUS: complete`.
The autonomous loop will start the review session next; no further
milestone session will read this guidance, but the review session and
any human operator will.

Deferred items surfaced during M3 (candidates for a future initiative):

- **JSON-lines tracer back-end.** `StderrTracer` writes human-readable
  lines. A future `JsonlTracer` (or `OpenTelemetryTracer`) would let the
  demo emit machine-readable events and remove the `_parse_trace_events`
  re-parsing currently in `visibility_full_demo.py`.
- **A `/trace` REPL slash command.** Static `--verbose` is sufficient
  today, but mid-session toggling would help operators who realise after
  several turns that they want to start capturing the trace stream.
- **Semantic memory selector.** `MemorySelector` is lexical Jaccard; a
  BM25 or embedding-based selector would be a more useful real-world
  demo of `ProjectMemory` and would let the visibility demo's auto-learn
  cue surface more interesting `memory_select` events.
- **`summary.md` "best event" column.** Currently shows the first event
  per channel; surfacing a representative event (largest externalized
  bytes, largest compacted message count) would tell a tighter story
  for `compact` and `externalize` rows.
- **Real-key end-to-end smoke run.** The autonomous-loop gate cannot
  consume API quota; running with a real `OPENAI_API_KEY` is the
  remaining manual verification the operator should do before declaring
  the initiative shipped externally.

The full M3 prompt is at:
`initiatives/current/prompts/M3.md`
