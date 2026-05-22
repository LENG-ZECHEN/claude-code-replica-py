---
slug: observable-thresholds
commit_prefix: obs-thr

milestones:
  M1:
    name: trace-hooks-and-verbose-flag
    phase_ids: [V1, V2]
    exit_gate: |
      `simple-agent --repl --verbose` after several turns: stderr
      contains at least one `[trace] [budget]` line and at least one
      `[trace] [memory_select]` line. Without `--verbose`, stderr is
      silent. `pytest --tb=no -q` is green with total >= 540. `mypy
      src` and `ruff check .` are clean.
    notes: |
      Create `src/simple_coding_agent/trace.py` exposing a `Tracer`
      Protocol with two implementations: `NullTracer` (default,
      no-op, zero overhead) and `StderrTracer` (writes a single
      line per event to `sys.stderr`).

      Wire `Tracer` via constructor injection into: `AgentLoop`,
      `ContextBuilder`, `ToolResultStore`, `ProjectMemory`,
      `ClaudeMdLoader`, `MicroCompactor`, `SnipTool`,
      `ContextCompactor`. For `auto_learn.detect_cue`, extend the
      function signature to `detect_cue(text, tracer=None)` and
      update both call sites (`cli.py` and `openai_cli.py`).

      Trace line format is locked to:
        [trace] [<channel>] key=value key=value ...
      Channels (must match `MetricsCollector` counter names where
      they overlap): `compact`, `reactive`, `microcompact`, `snip`,
      `externalize`, `memory_select`, `claude_md`, `auto_learn`,
      `budget`.

      Hard rule: trace lines MUST NOT contain raw user input or
      raw LLM output text. Only metadata (counts, token estimates,
      entry names, scores, tool ids). Add at least one test that
      asserts a sensitive substring fed through the loop does NOT
      appear in captured stderr.

      Order of operations at each fire site: perform the action ->
      `tracer.emit(...)` -> `metrics.record_*()`. Tracer is an event
      stream, MetricsCollector is the post-hoc counter; they coexist
      rather than replace each other.

      Add `--verbose` flag (argparse `action="store_true"`) to both
      `cli.py` and `openai_cli.py`. `_build_repl_loop` (cli.py) and
      `_run_openai_repl` (openai_cli.py) pick `StderrTracer()` when
      the flag is set, otherwise `NullTracer()`. The default
      production path constructs `NullTracer()`, so all existing 497
      tests must remain green with zero regressions.

      New tests: `tests/test_trace.py` (~10 cases covering NullTracer
      no-op behavior, StderrTracer line format, channel name
      coverage, and one secret-leak negative test). Add ~5 cases
      across `tests/test_cli.py`, `tests/test_repl.py`,
      `tests/test_openai_cli_repl.py` to cover the `--verbose` flag
      wiring and the default-silent path.

  M2:
    name: aggressive-thresholds-preset
    phase_ids: [V3]
    exit_gate: |
      `simple-agent --repl --verbose --aggressive-thresholds`
      running 8 turns that include repeated `read_file` calls
      produces at least one `[trace] [compact]` line and at least
      one `[trace] [snip]` line on stderr. Without
      `--aggressive-thresholds`, the same 8-turn input produces zero
      `[trace] [compact]` and zero `[trace] [snip]` lines. The REPL
      startup banner includes a single line summarizing the active
      preset, prefixed `[aggressive-thresholds]`. `pytest --tb=no -q`
      total >= 545. `mypy src` and `ruff check .` are clean.
    notes: |
      Add a module-level dict `_AGGRESSIVE_THRESHOLDS` at the top of
      `cli.py`:
        compact_threshold: 0.2           (default 0.8)
        keep_recent: 2                   (default 4)
        microcompact_minutes: 1          (default 60)
        max_inline_chars: 2_000          (default 50_000)
        total_budget_chars: 8_000        (default 200_000)
        snip_keep_recent: 1              (default 3)
        context_tokens: 4_000            (default 200_000)
        reserved_output_tokens: 512      (default 8_192)

      Add `--aggressive-thresholds` flag (argparse `store_true`) to
      both `cli.py` and `openai_cli.py`. When set, `_build_repl_loop`
      passes these values into `ContextBudget`, `ContextCompactor`,
      `MicroCompactor`, `ToolResultStore`, and `SnipTool` at
      construction time.

      Precedence rule: an explicit `--max-context-tokens` /
      `--reserved-output-tokens` / `--max-steps` from the user
      always overrides the preset value for that single field. Only
      the unspecified fields take the aggressive value. Test this
      explicitly.

      `snip.py` needs a small refactor first: extract `keep_recent`
      as a constructor parameter on `SnipTool` with default value 3
      so existing behavior is unchanged. Internal algorithm uses
      `self._keep_recent` instead of the current hard-coded
      constants. Existing `tests/test_snip.py` cases must remain
      green at default; add 1-2 new cases for `keep_recent=1`.

      Banner format (printed once at REPL start when the preset is
      active):
        [aggressive-thresholds] compact=0.2, microcompact=1min,
          inline=2k, total=8k, snip_keep=1, ctx=4k, out=512

      New example: `examples/aggressive_thresholds_demo.py` (~80
      LoC) -- MockProvider-based, deterministic, demonstrates the
      flag wiring without a network call.

      New tests: ~5 cases across `tests/test_repl.py` and
      `tests/test_openai_cli_repl.py` covering flag wiring,
      banner emission, precedence rule (explicit flags override
      preset), and `examples/aggressive_thresholds_demo.py`
      end-to-end behavior.

  M3:
    name: real-api-visibility-demo-and-guard
    phase_ids: [V4, V5]
    exit_gate: |
      Running `python examples/visibility_full_demo.py
      --confirm-api-call` with `OPENAI_API_KEY` or
      `DASHSCOPE_API_KEY` set produces a directory
      `examples/_artifacts/visibility-demo-YYYYMMDD-HHMMSS/`
      containing four non-empty files: `transcript.txt`,
      `trace.stderr`, `metrics.json`, `summary.md`. Without
      `--confirm-api-call`, the script exits with code 2 and prints
      an explanatory message. With `--confirm-api-call` but no API
      key in env, the script exits with code 3 and prints an
      explanatory message. `tests/test_visibility_full_demo.py`
      (key-less path, using the `_ExplodingProvider` pattern from
      `tests/test_openai_chat_demo.py`) verifies the script never
      constructs a real provider in its safe-by-default
      configuration. `pytest --tb=no -q` total >= 550. `mypy src`
      and `ruff check .` are clean.
    notes: |
      Main script: `examples/visibility_full_demo.py` (~200 LoC).
      Structure:

      1. `argparse` requires `--confirm-api-call`; missing flag ->
         print explanation -> `sys.exit(2)`.
      2. Check `OPENAI_API_KEY` or `DASHSCOPE_API_KEY` is set;
         missing -> print explanation -> `sys.exit(3)`.
      3. Create artifact directory
         `examples/_artifacts/visibility-demo-<ISO-timestamp>/`.
      4. Instantiate `StderrTracer(stream=open(.../trace.stderr,
         "w"))` plus `OpenAIProvider` plus `AgentLoop`, all wired
         with the `cli._AGGRESSIVE_THRESHOLDS` preset values.
      5. Drive a 3-turn scripted conversation designed to exercise
         as many mechanisms as possible:
            turn 1: read a fixed ~10KB file in the repo (triggers
                    `externalize`)
            turn 2: read the same file again (triggers `snip`)
            turn 3: "Please remember I prefer Python from now on"
                    (mixed Chinese/English text triggers
                    `auto_learn` cue + `ProjectMemory` write +
                    `memory_select` on the next provider call)
      6. After the loop exits, write four artifacts:
            - `metrics.json` -- `LoopResult.metrics` serialized
            - `transcript.txt` -- `Transcript.to_jsonable` rendered
              human-readable
            - `trace.stderr` -- already written live by StderrTracer
            - `summary.md` -- generated from metrics + tracer events,
              one row per channel showing trigger count and first
              fire site, plus a tokens-per-turn line
      7. Add `examples/_artifacts/*/` to `.gitignore` so artifacts
         do NOT enter version control. The `.gitignore` change MUST
         land in the same M3 commit; otherwise RUNBOOK Phase 1
         pre-flight will reject the next initiative because of a
         dirty working tree.

      Test file: `tests/test_visibility_full_demo.py` reuses the
      `_ExplodingProvider` + `monkeypatch` pattern from
      `tests/test_openai_chat_demo.py`. About 6 cases covering:
         (a) missing `--confirm-api-call` -> exit code 2 AND no
             provider constructed
         (b) missing API key -> exit code 3
         (c) with `--confirm-api-call` and mocked `OpenAIProvider`,
             all four artifact files exist and are non-empty
         (d) trace.stderr contains at least one `[trace] [budget]`
             line and one `[trace] [externalize]` line
         (e) summary.md is well-formed markdown with one row per
             channel
         (f) `.gitignore` contains `examples/_artifacts/`

      After M3 commits, append one row to README.md's "Examples"
      section describing `visibility_full_demo`. Phase 2C Tier A
      auto-apply may also catch this, but call it out explicitly in
      the M3 prompt to avoid relying on the auto-apply.
---
> Bootstrapped on 2026-05-22. Baseline commit: 2d414d91da65cc5998563e9c63b2d2be7028315d. Baseline pytest: 520 passing.

# Goal

Make the context-management subsystem (full-compact, micro-compact,
snip, reactive-compact, tool-result externalize) and the memory
subsystem (SessionMemory, ProjectMemory, MemorySelector,
ClaudeMdLoader, auto-learn cue) of `simple_coding_agent` visible in
real time during CLI sessions, easy to trigger via a one-shot preset
flag, and demonstrable end-to-end through a real-API demo script
that persists complete evidence to disk.

Three deliverables:

1. `--verbose` flag that streams `[trace]` event lines to stderr at
   every fire site.
2. `--aggressive-thresholds` preset flag that lowers every relevant
   threshold to demo-friendly values in a single switch.
3. `examples/visibility_full_demo.py` running against a real OpenAI
   or Dashscope endpoint, saving transcript + trace + metrics +
   human-readable summary into a timestamped artifact directory.

# Background / motivation

The previous initiative (`runtime-activation`, completed
2026-05-21, commit `de3ecad`) shipped the five milestones M1-M5
that took the P1-P8 context and memory mechanisms from
"unit-tested but runtime-unreachable" to "reachable in REPL and
countable via `/stats`". `MetricsCollector` answers "after the
fact, did this mechanism fire?", but it does NOT answer "while I am
talking to the agent right now, what is happening under the hood?"

Concrete pain points this initiative closes:

- A user running `simple-agent --repl` for 40 minutes has no way to
  know in real time whether full-compact fired in a specific turn;
  they must `/exit` and inspect `/stats` to find out, which loses
  the context of WHICH turn triggered it.
- `MemorySelector` selects top-5 entries by Jaccard score on every
  turn but the scores and ranking are completely opaque.
- The default thresholds (compact 0.8, microcompact 60 min, inline
  50_000 chars) almost never fire in normal conversation, so
  demonstrating these mechanisms to a third party requires
  hand-crafting a 200KB stress fixture -- there is no quick way to
  show "here is full-compact running on a real chat".
- The real-API CLI (`openai_cli.py`) already has REPL mode after M5,
  but no demo script exists that exercises a representative slice of
  the pipeline end-to-end and saves the result for sharing.

Doing the three things together turns the whole subsystem into
something you can see, trigger easily, and demo.

# Design sketch

**Tracer module.** New file `src/simple_coding_agent/trace.py`
defines a `Tracer` Protocol with a single method
`emit(channel: str, **fields)` and provides `NullTracer` (default,
no-op) and `StderrTracer` (writes
`[trace] [<channel>] k=v k=v\n` lines to a given stream, default
`sys.stderr`). The Protocol design lets future implementations
(JSON-lines, OpenTelemetry, log file) plug in without touching
fire sites.

**Wiring.** Tracer is injected via constructor into eight
components: `AgentLoop`, `ContextBuilder`, `ToolResultStore`,
`ProjectMemory`, `ClaudeMdLoader`, `MicroCompactor`, `SnipTool`,
`ContextCompactor`. For `auto_learn.detect_cue` (a pure function,
no `self`), the signature is extended to
`detect_cue(text, tracer=None)`. The default value at every site
is `NullTracer()`, so the production code path has zero behavioral
change and zero overhead.

**Fire-site ordering.** At every mechanism (compact, microcompact,
snip, externalize, memory_select, auto_learn cue, claude_md load,
budget assembly), the order is locked: perform the action ->
`tracer.emit(...)` -> `metrics.record_*()`. This guarantees that
the trace stream and counter stream stay consistent and lets the
demo's summary report cross-check them.

**Aggressive-thresholds preset.** A single dict
`_AGGRESSIVE_THRESHOLDS` in `cli.py` holds demo-friendly values for
every threshold (compact 0.2, microcompact 1 min, inline 2_000,
total 8_000, snip keep 1, ctx 4_000, reserved 512). The
`--aggressive-thresholds` flag in `_build_repl_loop` applies all of
them at once. An explicit `--max-context-tokens N` from the user
still overrides the preset for that field -- only the unspecified
fields use the aggressive value.

**SnipTool refactor.** Required by M2's exit gate
(`snip_keep_recent=1`). Currently `SnipTool` hard-codes per-tool
keep counts as `frozenset` literals; M2 extracts a
`keep_recent: int = 3` constructor parameter that drives the
algorithm. Default value preserves existing behavior; existing
`tests/test_snip.py` cases must remain green.

**Demo script.** `examples/visibility_full_demo.py` is a single
file under 200 LoC. Hard `--confirm-api-call` gate (same pattern as
`examples/openai_chat_demo.py`) prevents accidental network calls
in CI or tests. It writes four artifacts to a timestamped directory
under `examples/_artifacts/`: `transcript.txt`, `trace.stderr`,
`metrics.json`, `summary.md`. The summary is generated from
`MetricsCollector` counters and parsed trace events, so it is
self-validating against the live event stream.

# Risks / known unknowns

- **Eight-component injection surface.** Default `NullTracer` MUST
  be a strict no-op (every method body is `pass`, no lazy imports
  with side effects). M1's exit gate requires the existing 497-test
  suite to remain green at default; any single regression is an M1
  failure.

- **SnipTool refactor.** Extracting `keep_recent` touches the
  internal algorithm in `snip.py`. The default value 3 must be
  byte-equivalent in observable behavior to the current hard-coded
  constants. `tests/test_snip.py` is the verification surface.

- **Real-API cost.** `visibility_full_demo.py` consumes paid API
  quota. The `--confirm-api-call` gate is mandatory; tests use
  `_ExplodingProvider` to prove the safe-by-default path never
  constructs a real provider; a missing API key returns exit code 3
  rather than crashing.

- **Artifact directory in git.** `examples/_artifacts/*/` MUST be
  added to `.gitignore` in the same M3 commit. Otherwise the next
  RUNBOOK Phase 1 pre-flight check ("working tree clean except
  INBOX.md") will reject all future initiatives until the artifacts
  are cleaned.

- **Secret leakage via stderr.** Trace lines MUST NOT contain raw
  user input or raw LLM output text. M1 prompt explicitly requires
  one negative test that feeds a known sensitive substring through
  the loop and asserts it does NOT appear in captured stderr.

- **`auto_learn.detect_cue` signature extension.** Adding an
  optional `tracer=None` parameter is backward-compatible at the
  call-site level, but both existing callers (`cli.py` and
  `openai_cli.py`) need to be updated to pass through the tracer
  the REPL was built with. Easy to miss in review.

# Out of scope (this initiative)

- OpenTelemetry / structured-logging back-end for trace events.
  This initiative commits to human-readable stderr lines; a JSON or
  OTel emitter is a future initiative.
- Color / TUI rendering of trace lines (rich, textual). Plain text
  only for now.
- Embedding full transcript diffs or message bodies in trace lines.
  Leakage risk and excessive line length.
- A `/trace` REPL slash command to toggle verbose mid-session. The
  static `--verbose` flag is sufficient for this initiative;
  dynamic toggling is a candidate for a future initiative.
- Changes to `MetricsCollector` data shape or `/stats` output
  format. The tracer is additive and orthogonal.
- Exposing snip configuration beyond `keep_recent` as CLI flags.
  Wait for a real user need before broadening that surface.

# Anything else

**Execution-order constraint.** M1 must complete before M2 (M2's
exit gate requires the `[compact]` and `[snip]` channels to be
emittable). M2 must complete before M3 (M3's demo script imports
and uses `_AGGRESSIVE_THRESHOLDS`). RUNBOOK Phase 2 already runs
M1 -> M2 -> M3 in declaration order, so no extra coordination is
needed beyond keeping that order in the YAML above.

**Phase 2 trigger command.** Once Phase 1 bootstrap has been
committed, run:

    ./automation/scripts/run_all_milestones.sh

The script spawns one `claude --print` session per milestone plus
one final review session. On success the initiative is archived to
`initiatives/_archive/2026-05-observable-thresholds/`.

**Baseline numbers (for cross-checking).** At Phase 1 entry the
project should be at: pytest 520 passing, mypy clean, ruff clean,
on top of commit `2d414d9` (which adds the `/remember-session`
slash command and `shell_mode` plumbing on top of the previous
initiative's final commit `de3ecad`). Phase 1 will record the
exact baseline SHA into `config.yaml` and the PLAN.md provenance
header. M1 target >= 540, M2 target >= 545, M3 target >= 550.
