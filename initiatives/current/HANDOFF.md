# HANDOFF — Next: M2 (aggressive-thresholds-precedence-matrix-and-bug-fix)

> Updated by: `M1` session
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `obs-thr-harden`
- **current milestone**: just-completed `M1` — trace-robustness-and-leak-coverage
- **next milestone**: `M2` — aggressive-thresholds-precedence-matrix-and-bug-fix
- **all milestones (per PLAN)**: M1 [done], M2 [next], M3 [pending]

## 2. Completed milestones

### M1

- **commit**: `71d3c80` `[obs-thr-hd/M1] harden StderrTracer + expand leak/roundtrip coverage`
- **files changed**: `src/simple_coding_agent/trace.py`, `tests/test_trace.py`
- **tests added**: `tests/test_trace.py` (+27 cases: 13 `_render_value` units, 4-shape `test_secret_leak_negative` parametrize, 2 closed-stream guards, 1 reactive e2e, 1 whitespace roundtrip + 3 non-string roundtrip, 1 nine-channel scalar-format regression, plus helper-edge cases). Total: 557 → 584
- **behavior implemented**: `StderrTracer.emit` no longer crashes the
  agent turn when its stream is closed or the pipe is broken — the
  `self._stream.write(line)` call is wrapped in
  `try/except (OSError, ValueError): return` (only those two are
  swallowed; `KeyboardInterrupt`/`SystemExit`/other errors still
  propagate). A new module-level helper `_render_value(value)` renders
  each field value as a parse-stable token: scalars (`bool`/`int`/
  `float`/`None`) via `str()`, whitespace-free strings unchanged, and
  whitespace-containing strings or any non-scalar type via `repr()`
  (quoted). `emit` now reads field values through `_render_value`
  instead of the bare `fields[key]`, so a value with embedded spaces
  (e.g. a dict repr) can no longer silently corrupt the adjacent
  `k=v` field when read by `visibility_full_demo._parse_trace_events`.
- **design decisions (deviations from PLAN)**:
  - (none) — implemented exactly the two changes specified in PLAN.md /
    config.yaml. Added 27 tests vs the PLAN's "~8" estimate because the
    PLAN's enumerated list (4-shape parametrize + closed-stream +
    reactive-e2e + whitespace + non-string roundtrip + 9-channel
    regression + `_render_value` units + bool/int edges) naturally
    expands past 8 once each parametrize case is counted individually.
    Exit gate (≥565) is exceeded; no scope creep beyond `trace.py` +
    `test_trace.py`.
- **known limitations**:
  - `_render_value` for a whitespace-free **non-ASCII** string returns
    it unchanged (per PLAN's literal rule "str without whitespace →
    value"), so the line is not guaranteed pure-ASCII for such inputs.
    In practice fire sites emit only metadata (counts, IDs, scores), so
    non-ASCII field values do not occur. Not a regression.

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `71d3c80` — `git -C python-replica show 71d3c80`
- **tests**: 584 passing (was 557 at baseline, delta +27)
- **mypy**: clean
- **ruff**: clean
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that `M2` and subsequent milestones MUST respect. Update by
> ADDING — only remove a constraint by quoting it and explaining why it
> is retired.

Initiative-level invariants from PLAN.md "Anything else" (still in force):

- Do not change the 9-channel list (`compact`, `reactive`,
  `microcompact`, `snip`, `externalize`, `memory_select`, `claude_md`,
  `auto_learn`, `budget`).
- Do not add or remove keys from `_AGGRESSIVE_THRESHOLDS` (values may be
  tuned but the 8-key set is frozen).
- Do not change the `NullTracer.emit` body — it must remain literally
  `pass`.
- Do not introduce new dependencies (the M3 perf assertion uses stdlib
  `timeit`; do not add `pytest-benchmark`, `freezegun`, etc.).

New constraints added by `M1`:

- **do not modify**:
  - `StderrTracer.emit` MUST keep the `(OSError, ValueError)` guard on
    the `write` call (`src/simple_coding_agent/trace.py`). Removing it
    re-introduces the closed-stream crash that M1 fixed. Do not widen it
    to bare `except Exception:` — `KeyboardInterrupt`/`SystemExit` must
    propagate.
- **preserve**:
  - `_render_value` helper in `trace.py` is now part of the internal
    interface that M3's demo-parser tolerance work depends on. Do not
    rename it or change its semantics in M2/M3 without coordinating: M3
    extends `visibility_full_demo._parse_trace_events` to read the
    repr-quoted form M1 produces.
- **compatibility requirements**:
  - The locked scalar line format `[trace] [<channel>] k=v ...` is
    byte-identical for scalar values (regression-pinned by
    `test_nine_channel_format_unchanged_for_scalar_values`). Only
    whitespace/non-scalar values gained repr-quoting.

## 5. Next milestone guidance

For `M2` — aggressive-thresholds-precedence-matrix-and-bug-fix:

- **next scope**: Fix the real bug where `_AGGRESSIVE_THRESHOLDS["context_tokens"]`
  and `["reserved_output_tokens"]` are always shadowed by the argparse
  defaults (`200_000` / `8_192`) in `_run_repl`, so 2 of the 8 preset
  fields never take effect. Change those argparse defaults (and
  `--max-steps` if applicable) to a `None` sentinel, add module-level
  `_DEFAULT_MAX_CONTEXT_TOKENS = 200_000`, `_DEFAULT_RESERVED_OUTPUT_TOKENS = 8_192`,
  `_DEFAULT_MAX_STEPS = 50`, and apply a three-way decision at the top
  of `_run_repl` (user-explicit > preset > built-in default). Mirror the
  exact same sentinel logic in `openai_cli._run_openai_repl` so the two
  REPLs stay symmetric. Add a `MicroCompactor(threshold_minutes < 1)`
  `ValueError` guard mirroring `SnipTool(keep_recent=0)`. Add the new
  precedence line to `--help`.
- **relevant files**:
  - `src/simple_coding_agent/cli.py` — sentinel handling in `_run_repl`;
    reuse the `_LAST_LOOPS` hook (cli.py:161) + `_build_repl_loop` for
    the matrix assertions.
  - `src/simple_coding_agent/openai_cli.py` — mirror the same logic in
    `_run_openai_repl`.
  - `src/simple_coding_agent/compact.py` — `MicroCompactor.__init__`
    ~3-line guard.
  - `tests/test_repl.py`, `tests/test_openai_cli_repl.py`,
    `tests/test_compact.py`.
- **expected tests**:
  - `tests/test_repl.py` — a `@pytest.mark.parametrize` precedence
    matrix over all 8 `_AGGRESSIVE_THRESHOLDS` fields × 3 states
    (default-only, preset-active, explicit-override; flag-less fields
    only need states i+ii).
  - `tests/test_compact.py` — one `pytest.raises(ValueError)` for
    `MicroCompactor(threshold_minutes=0)`.
  - `tests/test_openai_cli_repl.py` — at least one symmetry case proving
    `openai_cli`'s sentinel handling matches `cli`'s.
  - pytest 584 → keep a +12 minimum (PLAN's ≥577 was measured from its
    own 565 baseline; re-measure from the actual 584).
- **risks**:
  - Changing argparse defaults to `None` is user-visible. Run
    `grep -rn "200_000\|8_192" tests/` first — expect 2-4 existing tests
    that assert the old defaults and will need updating in M2.
  - **M1 overlap check**: M1's new `test_trace.py` cases use trace field
    names `count`, `tokens`, `payload`, `z`, `dropped` and channels
    `budget`/`reactive` — none overlap M2's `_AGGRESSIVE_THRESHOLDS`
    field names (`compact_threshold`, `keep_recent`,
    `microcompact_minutes`, `max_inline_chars`, `total_budget_chars`,
    `snip_keep_recent`, `context_tokens`, `reserved_output_tokens`). No
    collision; M2 need not touch `test_trace.py`.
  - Do NOT touch `trace.py` in M2 (M1 owns it; M3 depends on its
    `_render_value` contract).

The full ready-to-run prompt is at:
`initiatives/current/prompts/M2.md`
