---
slug: obs-thr-harden
commit_prefix: obs-thr-hd

milestones:
  M1:
    name: trace-robustness-and-leak-coverage
    phase_ids: [A1, A2]
    exit_gate: |
      `pytest --tb=no -q` is green with total >= 565 (baseline 557, +8).
      `tests/test_trace.py` must include the following new coverage:
      (a) >= 3 parametrize cases covering different secret shapes
          (Bearer token, AWS access key, long OpenAI key,
          Unicode username / Chinese-character secret string).
          None of the secret substrings may appear in captured stderr
          after the value passes through the REPL.
      (b) one stream-closed negative test: construct an already-closed
          `io.StringIO`, call `StderrTracer(stream=closed).emit("budget", ...)`
          and assert no `ValueError` / `OSError` propagates and the agent
          does not crash.
      (c) one reactive end-to-end test: a MockProvider whose first call
          raises `PromptTooLongError` and whose second call succeeds;
          run a one-turn CLI REPL session and assert captured stderr
          contains at least one `[trace] [reactive]` line.
      (d) one value-with-whitespace test: emit a field whose value
          contains whitespace (for example `tracer.emit("budget",
          payload={"a": 1, "b": 2})`); the emitted line, when parsed by
          `examples/visibility_full_demo._parse_trace_events`, must not
          break adjacent fields.
      `mypy src` and `ruff check .` are clean.
    notes: |
      Touch list (ceiling):
        src: src/simple_coding_agent/trace.py (core change)
        test: tests/test_trace.py
      Do NOT touch cli.py / openai_cli.py / any of the other 9 fire-site
      components, do NOT change the `Tracer` Protocol signature, do NOT
      change `NullTracer.emit` body (it must remain literally `pass`).

      Change 1: wrap `StderrTracer.emit`'s `self._stream.write(line)` in
        `try: ... except (OSError, ValueError): return`
      Catch only `OSError` / `ValueError` (covers "I/O on closed file"
      and broken-pipe). Do NOT catch `KeyboardInterrupt` / `SystemExit`
      or `Exception`. `flush` is already defensive — leave it alone.

      Change 2: add a module-level helper `_render_value(value)`:
        - bool / int / float / None  → `str(value)`
        - str without whitespace     → `value`
        - str with whitespace, OR any other type → `repr(value)` (quoted)
      Replace the bare `fields[key]` read in `emit` with this helper.
      Keep the line ASCII so `visibility_full_demo._parse_trace_events`
      keeps working; M3 will extend that parser to tolerate the quoted
      form.

      Reactive end-to-end fixture: a MockProvider subclass whose Nth
      call raises `PromptTooLongError` and others return normally. The
      pattern already exists in `tests/test_stress_full_compact.py` —
      reuse rather than reinvent.

      Test cases added (~8): 4-shape secret-leak parametrize counts as
      one parametrize block + closed-stream + reactive-e2e +
      whitespace-roundtrip + non-string value (dict / list / None)
      roundtrip + a 9-channel format regression + `_render_value`
      unit tests + bool/int edge cases.

      Risk assessment: touches 1 src + 1 test only. Single-file
      deep-hardening. No cross-component wiring, no new Protocol, no
      CLI surface change. Every red line from the M1-243-turn lesson
      (>6 src / >4 components changing protocol / >15 tests / the
      "abstraction + wire + CLI" triple-combo) is far below threshold.

      pytest baseline: 557 → >= 565 (+8 minimum).

  M2:
    name: aggressive-thresholds-precedence-matrix-and-bug-fix
    phase_ids: [B1, B2, B3]
    exit_gate: |
      `pytest --tb=no -q` is green with total >= 577 (after M1, 565, +12).
      `tests/test_repl.py` must contain a `@pytest.mark.parametrize`
      matrix covering the effective value of every field in
      `_AGGRESSIVE_THRESHOLDS` (all 8 keys) under three states:
        (i)   user passes no relevant flag, no --aggressive-thresholds
              → expected: the `_DEFAULT_*` constant
        (ii)  user passes no relevant flag, --aggressive-thresholds set
              → expected: `_AGGRESSIVE_THRESHOLDS[<field>]`
        (iii) user passes the relevant flag explicitly,
              --aggressive-thresholds also set
              → expected: the user's explicit value (preset overridden)
      Field set: compact_threshold, keep_recent, microcompact_minutes,
        max_inline_chars, total_budget_chars, snip_keep_recent,
        context_tokens, reserved_output_tokens.
      Fields without a CLI flag backing (snip_keep_recent,
      max_inline_chars, etc.) only need states (i) and (ii).
      `MicroCompactor(threshold_minutes=0)` must raise `ValueError`
      mirroring `SnipTool(keep_recent=0)`; `tests/test_compact.py`
      gains one negative test.
      `tests/test_openai_cli_repl.py` must include at least one case
      verifying that `openai_cli`'s sentinel handling matches `cli`'s
      (so the two REPLs cannot drift apart).
      `mypy src` and `ruff check .` are clean.
    notes: |
      Touch list (ceiling):
        src: src/simple_coding_agent/cli.py (sentinel handling in
             `_run_repl`), src/simple_coding_agent/openai_cli.py
             (mirror the same logic), src/simple_coding_agent/compact.py
             (`MicroCompactor.__init__` ~3-line guard)
        test: tests/test_repl.py, tests/test_openai_cli_repl.py,
              tests/test_compact.py
      Do NOT touch trace.py, do NOT touch the 9-channel list, do NOT
      add or remove keys from `_AGGRESSIVE_THRESHOLDS` (values may be
      tweaked but the key set is frozen).

      Core bug fix (M2 MUST fix this — it is a real bug that was
      masked by the way the M3 demo reads the preset dict directly):

      Change the argparse defaults to a `None` sentinel:
        --max-context-tokens: default=None (was 200_000)
        --reserved-output-tokens: default=None (was 8_192)
        --max-steps: default=None (if applicable — confirm during prompt)
      At the top of `_run_repl`, unify a three-state decision:
        explicit_value = args.max_context_tokens  # or None
        if explicit_value is not None:
            ctx_tokens = explicit_value
        elif args.aggressive_thresholds:
            ctx_tokens = _AGGRESSIVE_THRESHOLDS["context_tokens"]
        else:
            ctx_tokens = _DEFAULT_MAX_CONTEXT_TOKENS
      Apply the same shape to the other two int flags. Add
      `_DEFAULT_MAX_CONTEXT_TOKENS = 200_000`,
      `_DEFAULT_RESERVED_OUTPUT_TOKENS = 8_192`, and
      `_DEFAULT_MAX_STEPS = 50` (if applicable) at module level so the
      old defaults are preserved as named constants.

      `--help` text gets one new line:
        "If --aggressive-thresholds is also set and you do not pass
         this flag, the preset value applies; otherwise the built-in
         default applies."

      `openai_cli.py` must mirror this change inside `_run_openai_repl`,
      otherwise the two REPLs drift and the review session will catch
      it immediately. The M5 P9 record explicitly states "the slash
      command surface is identical between MockProvider and live-
      provider REPLs" — sentinel handling must preserve that symmetry.

      MicroCompactor guard:
        if threshold_minutes < 1:
            raise ValueError(
                f"threshold_minutes must be >= 1, got {threshold_minutes}"
            )
      Add one `pytest.raises(ValueError)` case to `tests/test_compact.py`.

      Precedence matrix assertion strategy: construct a loop via
      `cli._build_repl_loop` directly, then read internal attributes
      (`loop._max_steps`, `loop._budget.max_tokens`,
      `loop._budget.reserved_output_tokens`, the underlying
      `_tool_result_store._max_inline_chars`,
      `loop._snip_tool._keep_recent`, etc.) and assert the expected
      effective value. The `_LAST_LOOPS` hook introduced in M1 of the
      previous initiative (cli.py:161) supports this — reuse it.

      Test cases added (~12): precedence matrix 8-10 rows +
      microcompact guard 1 + openai_cli symmetry 1-2.

      Regression scan checklist (the M2 prompt must include this):
        grep -rn "200_000\|8_192" /Users/leng/my-cc-py/python-replica/tests
      Find existing tests that rely on the old argparse defaults and
      update them (expect 2-4 hits).

      Risk assessment: touches 3 src + 3 test files. Per-file diff is
      small (~10 lines of sentinel logic in cli.py and openai_cli.py
      plus a module-level constant; +3 guard lines in compact.py).
      No new protocol, no new module, no `NullTracer.emit` change.
      Changing argparse defaults to `None` is a user-visible behavioural
      shift, but `--help` text is updated in sync and the change fixes
      a real bug (the preset never being honoured).

      pytest baseline: 565 → >= 577 (+12 minimum).

  M3:
    name: demo-fences-zero-overhead-and-doc-sync
    phase_ids: [C1, C2, C3]
    exit_gate: |
      `pytest --tb=no -q` is green with total >= 587 (after M2, 577, +10).
      `examples/visibility_full_demo.py` must:
      (a) `_new_run_dir` handles same-second timestamp collisions by
          appending a `-2` / `-3` ... `-9` suffix; if all 9 suffixes
          are taken in one second, exit non-zero with a clear message.
      (b) `_parse_trace_events` tolerates the repr-quoted values that
          M1 introduces (whitespace-containing strings, dict / list
          reprs).
      `tests/test_visibility_full_demo.py` adds:
        - a directory-collision case (two demo runs in the same second)
        - a parser-tolerates-quoted-values case
      `tests/test_trace.py` adds a `NullTracer` performance assertion:
        timeit 100_000 calls of `tracer.emit("compact", count=1,
        tokens=42)`; total elapsed must be < 20ms (mean < 200ns/call).
        Skip under coverage instrumentation (detect via
        `os.environ.get("COVERAGE_RUN")` or `sys.gettrace()`) so the
        gate doesn't false-fail under `pytest --cov`.
      `tests/test_cli.py` adds a `--help` snapshot test pinning the
      key phrases for --verbose, --aggressive-thresholds, and
      --max-context-tokens (including the M2-added precedence line).
      `README.md` "Examples" section must explicitly reference
      `aggressive_thresholds_demo.py` (currently absent) and
      `visibility_full_demo.py`.
      `python-replica/CLAUDE.md` "Implementation Roadmap" gets one new
      entry for this hardening initiative listing the SHA range and
      pytest delta.
      `mypy src` and `ruff check .` are clean.
    notes: |
      Touch list (ceiling):
        src: none (this milestone is doc + demo + test hardening only)
        examples: examples/visibility_full_demo.py (extend
                  `_new_run_dir` and `_parse_trace_events` only — do
                  NOT create new example files)
        test: tests/test_visibility_full_demo.py, tests/test_trace.py
              (perf assert), tests/test_cli.py (--help snapshot)
        docs: README.md, python-replica/CLAUDE.md
      Do NOT touch trace.py, do NOT touch cli.py / openai_cli.py (M2
      already did), do NOT introduce new dependencies (the perf assert
      uses the stdlib `timeit`).

      `_new_run_dir` collision logic:
        base = examples/_artifacts / f"visibility-demo-{timestamp}"
        if not base.exists():
            base.mkdir(parents=True)
            return base
        for suffix in range(2, 10):
            candidate = base.with_name(base.name + f"-{suffix}")
            if not candidate.exists():
                candidate.mkdir(parents=True)
                return candidate
        raise SystemExit(
            f"too many demo runs in the same second; clean "
            f"{base.parent} or wait a second"
        )

      `_parse_trace_events` quoted-value tolerance:
        The current implementation uses `token.partition("=")` plus a
        line-level `split()`, which assumes every value is whitespace-
        free. Change the scan so that, after `=`, if the next character
        is `'` or `"`, read until the matching closing quote (handles
        `repr({...})`-shaped values); otherwise split on the next
        whitespace as before. Preserve backward compatibility for
        unquoted values.

      `NullTracer` perf assertion:
        import timeit
        from simple_coding_agent.trace import NullTracer
        t = NullTracer()
        elapsed = timeit.timeit(
            lambda: t.emit("compact", count=1, tokens=42),
            number=100_000,
        )
        assert elapsed < 0.020, f"{elapsed=}s exceeds 20ms budget"
        Guard with a coverage-mode skip at the top of the test
        (`pytest.skip(...)` if `os.environ.get("COVERAGE_RUN")` set or
        `sys.gettrace() is not None`).

      `--help` snapshot test shape:
        Capture help text via `cli.main(["--help"])` + `SystemExit` +
        `capsys`. Assert it contains:
          "--verbose"
          either "Stream [trace]" or "verbose trace"
          "--aggressive-thresholds"
          "preset"
          "preset value applies"   (the M2-added wording)
        Pin key phrases, not the whole block, so future innocent
        help-text rewording doesn't break the snapshot.

      `README.md` "Examples" section:
        - Confirm `visibility_full_demo.py` is described (the previous
          M3 inbox requested this; verify and fix if missing).
        - Add a one-line link for `aggressive_thresholds_demo.py`.
        - Add `stress_demo.py` and `microcompact_demo.py` links if
          they are not already there.

      `python-replica/CLAUDE.md` "Implementation Roadmap" addition:
        - **observable-thresholds-harden initiative — M1–M3**
          (`<SHA1>`–`<SHA3>`, 2026-05-23). M1 hardens `trace.py`
          against closed streams and unsafe value serialisation; M2
          fixes the `_AGGRESSIVE_THRESHOLDS` bug where
          `context_tokens` / `reserved_output_tokens` were always
          shadowed by argparse defaults, and adds the full 8-field
          precedence matrix; M3 hardens `visibility_full_demo`
          against directory collision and parser fragility, asserts
          `NullTracer` zero overhead via timeit, and syncs README +
          CLAUDE.md. pytest 557 → ~587 (+30).

      Test cases added (~10): directory collision 1-2 + parser
      tolerance 2 + perf assert 1 + --help snapshot 2-3 + README
      reference check 1 + regression coverage 1-2.

      Risk assessment: zero source-code change. Surface is examples /
      docs / tests only — the lowest-risk milestone. The perf
      assertion is sensitive to interpreter version (Python 3.14 noop
      `emit` is ~50-100ns/call on the harness CI); the 200ns budget
      leaves 2-3x headroom and the test skips under coverage.

      pytest baseline: 577 → >= 587 (+10 minimum).
---
> Bootstrapped on 2026-05-23. Baseline commit: `e8e2206c2fc6737f509229b2414bb578dc4d99e1`. Baseline pytest: 557 passing. mypy: clean. ruff: clean. Branch: `main`.

# Goal

Harden everything `observable-thresholds` (M1+M2+M3, commits
`063d5d9`–`026db2e`, 2026-05-22) shipped — the `Tracer` Protocol +
`NullTracer` / `StderrTracer`, the `--verbose` and
`--aggressive-thresholds` CLI flags, and the
`examples/visibility_full_demo.py` artifact pipeline — so that the
"feature works in the happy path but is fragile at the edges" state
becomes "feature is sound and demonstrably so." This initiative is
deliberately scoped as a follow-up *quality pass*, not a feature
expansion. Concretely:

1. Fix one real bug: `_AGGRESSIVE_THRESHOLDS["context_tokens"]` and
   `_AGGRESSIVE_THRESHOLDS["reserved_output_tokens"]` are always
   shadowed by the argparse defaults in `_run_repl`, so 2 of the 8
   preset fields never take effect.
2. Extend the "explicit flag overrides preset" promise of
   `--aggressive-thresholds` from 1-field coverage to a full 8-field
   precedence matrix.
3. Add a closed-stream guard and safe non-string value rendering to
   `StderrTracer`; add input validation to `MicroCompactor` to mirror
   the existing guard in `SnipTool`.
4. Expand the trace secret-leak negative test from one secret shape
   to >= 4 (Bearer / AWS / long OpenAI / Unicode).
5. Harden the visibility demo against directory collisions and make
   its event parser tolerate the repr-quoted values M1 introduces.
6. Pin `NullTracer` zero-overhead as a timeit assertion
   (< 200ns/call mean).
7. Sync README + python-replica/CLAUDE.md.

# Background / motivation

Two of the three milestones in the previous initiative ran into
abnormal interruptions inside their `claude --print` session and had
to be manually recovered:

- M1 hit the Claude Code "context auto-compact 3 times → stop"
  guard at turn 243 (the milestone touched 11 src + 5 test files
  and wired a new `Tracer` Protocol through 8 components — too
  large for a single session).
- M2 was halted by an exhausted API balance partway through.

In both cases the milestone was completed by hand. The exit-ritual
records in `PROGRESS.md` still read "exit gate met", but
`REVIEW.md` Phase 2B-4 ("Failure-path coverage") only scored 4/5
and flagged that M1 shipped exactly one secret-leak negative test,
M2 verified the precedence rule on only one field, and M3's tests
only covered the exit-2/3 safety gates.

Worse, a real bug slipped through. `_run_repl` reads the argparse
defaults `max_context_tokens=200_000` and
`reserved_output_tokens=8_192` before applying the aggressive
preset, so the preset values `4_000` / `512` for those two keys are
never honoured. `aggressive_thresholds_demo.py` and
`visibility_full_demo.py` both read `_AGGRESSIVE_THRESHOLDS`
directly and so masked the bug.

On top of that, `StderrTracer.emit` writes to its stream without an
exception guard (a closed file handle would crash the agent turn —
a trace surface is advisory output and must not propagate writer
errors), the demo's `_parse_trace_events` splits on whitespace and
breaks on any value that contains a space, and
`MicroCompactor(threshold_minutes=0)` builds fine even though the
equivalent `SnipTool(keep_recent=0)` raises. These are textbook
"works on the happy path, brittle at the corners" smells.

This initiative is deliberately scoped as a *quality consolidation*
pass, not a feature expansion.

# Design sketch

Three milestones, every one targeted at hardening, with the touch
surface kept far below the 11-src/5-test water mark that triggered
M1's 243-turn auto-compact protection last time.

**M1 (trace.py robustness).** One source file + one test file.
`StderrTracer.emit` wraps `self._stream.write(line)` in
`try: ... except (OSError, ValueError): return`. A new module-level
helper `_render_value` formats whitespace-containing strings and
non-stringable types via `repr()` so the line stays ASCII and
parseable. `tests/test_trace.py` parametrizes the secret-leak case
across 4-5 realistic shapes (Bearer / AWS / long OpenAI / Chinese
Unicode), adds a closed-stream negative test, a reactive end-to-end
test (MockProvider raises `PromptTooLongError` on first call, then
succeeds — assert `[trace] [reactive]` appears in captured stderr),
and a whitespace-roundtrip test verifying the demo parser still
handles the new repr-quoted format.

**M2 (aggressive-thresholds precedence + bug fix).** Three src
(`cli.py`, `openai_cli.py`, `compact.py`) + three test files. The
`--max-context-tokens`, `--reserved-output-tokens`, and
`--max-steps` argparse defaults become `None` sentinels; `_run_repl`
performs an explicit three-way decision (user-explicit beats
preset, preset beats built-in default). Module-level
`_DEFAULT_MAX_CONTEXT_TOKENS` etc. preserve the old numeric
defaults. `MicroCompactor.__init__` adds `if threshold_minutes < 1:
raise ValueError(...)` to mirror `SnipTool`. A
`pytest.mark.parametrize` matrix in `tests/test_repl.py` covers all
8 `_AGGRESSIVE_THRESHOLDS` fields across the three states
(default-only, preset-active, explicit-override). `openai_cli` gets
the symmetric sentinel logic and a symmetry test in
`tests/test_openai_cli_repl.py`.

**M3 (demo fences, zero-overhead, doc sync).** Zero source-code
change. `examples/visibility_full_demo.py` extends `_new_run_dir`
with a `-N` suffix retry for same-second collisions and extends
`_parse_trace_events` to tolerate repr-quoted values from M1. A
new `NullTracer` perf assertion in `tests/test_trace.py` runs
`timeit` 100_000 times and asserts the total elapsed under 20ms
(skipped under coverage instrumentation). A `--help` snapshot test
in `tests/test_cli.py` pins the key phrases for `--verbose`,
`--aggressive-thresholds`, and `--max-context-tokens` so future
help-text drift can't silently lose the precedence note M2 added.
`README.md` "Examples" gets the missing `aggressive_thresholds_demo.py`
link and `python-replica/CLAUDE.md` Implementation Roadmap gets a
new bullet for this initiative.

The 9 fire-site components (`context.py`, `claude_md.py`,
`memory.py`, `compact.py` outside `MicroCompactor`,
`tool_result_store.py`, `snip.py`, `auto_learn.py`, `loop.py`) are
not touched. The 9-channel name list is frozen. The 8-key
`_AGGRESSIVE_THRESHOLDS` dictionary keys are frozen (values may be
tweaked).

# Risks / known unknowns

- **Changing argparse defaults to `None` is a user-visible
  behavioural shift.** `--help` output changes (fixed in the M3
  snapshot test). Some existing tests in `test_cli` / `test_repl`
  compare directly against `200_000` / `8_192` and will need updates
  (M2 includes a `grep -rn "200_000\|8_192" tests/` regression scan
  in its prompt). Treat this as a compatible adjustment — the change
  fixes a real bug where the preset never took effect.
- **The `NullTracer` perf assertion is interpreter-sensitive.**
  Python 3.14 noop emit is roughly 50-100ns/call on the harness CI;
  the 200ns budget leaves 2-3x headroom and the test skips under
  `pytest --cov` to avoid false positives from coverage instrumentation.
- **`try: write except (OSError, ValueError)` must not catch
  `KeyboardInterrupt` / `SystemExit`.** The tracer is advisory output,
  but it must not suppress control-flow signals.
- **`openai_cli` and `cli` must keep their sentinel logic
  symmetric.** Any drift will be flagged by the review session. M2's
  prompt must mention this explicitly so both files land in the same
  commit.
- **The repr-quoted value format from M1 changes the trace line
  shape.** `visibility_full_demo._parse_trace_events` must be extended
  in M3 in the same release, otherwise the M1 whitespace-roundtrip
  test will not pass. This creates an implicit M1 → M3 dependency;
  M2 does not touch either path.
- **Adding `MicroCompactor` `ValueError` for `threshold_minutes < 1`.**
  No existing call site uses 0 or a negative — the default 60 and the
  preset 1 both satisfy `>= 1`. Confirm via grep that no fixtures
  pass an out-of-range value before tightening.
- **README edits may collide with the codemap auto-apply.** Check
  `automation/templates/review.md` Tier A scope — if the Examples
  section is overwritten by the review session's auto-apply, the M3
  edit must land in a way the auto-apply preserves (or the auto-apply
  rule needs to be tightened in scope).

# Out of scope (this initiative)

Inherits the previous initiative's exclusions and adds new explicit ones:

- No JSONLines / OpenTelemetry / OTLP trace output format. No
  dynamic `/trace` slash command. No `ColorizedTracer` / TUI
  rendering. No `snip` CLI flag exposure. No tracer level / channel
  filter mechanism.
- No new example file. `aggressive_thresholds_demo.py`,
  `stress_demo.py`, `microcompact_demo.py`, and
  `visibility_full_demo.py` retain their existing shapes. Only
  `visibility_full_demo.py` may be edited, and only `_new_run_dir`
  and `_parse_trace_events`.
- No change to the 9-channel list. No add / remove of
  `_AGGRESSIVE_THRESHOLDS` keys (values may be tuned but the key set
  is frozen). No change to the `Tracer` Protocol signature. No
  change to the `NullTracer.emit` body (it must remain `pass`).
- No new dependencies. No `pytest-benchmark`, no `freezegun`, no
  test runner additions — the perf assertion uses stdlib `timeit`.
- No rewrite of `PROGRESS.md` / `HANDOFF.md` history. No SHA
  corrections in the archived `_archive/2026-05-observable-thresholds/`
  directory.
- No real-API path. All tests use `MockProvider` or stubs.
- No change to `metrics.json` field set. No change to `summary.md`
  table columns.
- No new `Tracer` implementations (`CompositeTracer`,
  `JSONLinesTracer`, `OTelTracer`, etc.).
- No change to `MetricsCollector` data shape or `/stats` output
  format.

# Anything else

**Hard ordering constraint.** M1 must land before M3, because M1's
`_render_value` change alters the emit field serialisation
(whitespace-containing values become repr-quoted) and M3's
`_parse_trace_events` tolerance test depends on the new shape. M2
changes the argparse default sentinels and triggers updates to a
handful of existing `test_cli` / `test_repl` cases; those updates
must land in M2, not be left for M3. M3 is intentionally last as
the doc-sync + perf-assertion wrap-up. RUNBOOK Phase 2 already
serialises milestones in YAML declaration order, so no extra
coordination is needed.

**Hard invariants every milestone prompt must echo in its
`§Out of scope` block (4 lines):**

1. Do not change the 9-channel list.
2. Do not add or remove keys from `_AGGRESSIVE_THRESHOLDS`.
3. Do not change `NullTracer.emit` body — it must remain `pass`.
4. Do not introduce new dependencies.

**Baseline (filled by Phase 1, 2026-05-23):**

- baseline commit SHA: `e8e2206c2fc6737f509229b2414bb578dc4d99e1`
- baseline pytest count: 557 (matches the `observable-thresholds`
  end-state)
- baseline mypy: clean. baseline ruff: clean. branch: `main`.
- per-milestone targets: M1 >= 565, M2 >= 577, M3 >= 587

Every M's notes is kept within the 50-100 line budget. Touch
surface is `<= 4 src + <= 4 test` per milestone, far below the
11-src / 5-test water mark that triggered the 243-turn auto-compact
protection in the previous initiative's M1.

**Phase 2 trigger command** (same as before):

    cd /Users/leng/my-cc-py
    ./python-replica/automation/scripts/run_all_milestones.sh
