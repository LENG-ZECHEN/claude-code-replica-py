# HANDOFF — Next: M3 (demo-fences-zero-overhead-and-doc-sync)

> Updated by: `M2` session
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `obs-thr-harden`
- **current milestone**: just-completed `M2` — aggressive-thresholds-precedence-matrix-and-bug-fix
- **next milestone**: `M3` — demo-fences-zero-overhead-and-doc-sync
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [next]

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

### M2

- **commit**: `30945de` `[obs-thr-hd/M2] fix preset bug + 8-field precedence matrix + MicroCompactor guard test`
- **files changed**: `src/simple_coding_agent/cli.py`,
  `src/simple_coding_agent/openai_cli.py`, `tests/test_repl.py`,
  `tests/test_openai_cli_repl.py`, `tests/test_compact.py`
- **tests added**: `tests/test_repl.py` (+18 — the 8-field × 3-state
  `test_aggressive_thresholds_precedence_matrix`: 8 default + 8 preset +
  2 explicit for the two flag-backed fields), `tests/test_compact.py`
  (+1 — `test_microcompactor_rejects_zero_minutes`),
  `tests/test_openai_cli_repl.py` (+2 — sentinel symmetry: aggressive
  budget matches cli, explicit budget overrides preset like cli).
  Total: 584 → 605 (+21).
- **behavior implemented**: The real bug is fixed — with
  `--aggressive-thresholds` and no explicit budget flag, the REPL now
  honours the preset's `context_tokens=4_000` /
  `reserved_output_tokens=512` instead of the argparse defaults
  `200_000` / `8_192` that previously shadowed them. The argparse
  defaults for `--max-context-tokens`, `--reserved-output-tokens`, and
  `--max-steps` are now `None` sentinels in both `cli.py` and
  `openai_cli.py`. A new module-level helper
  `cli._resolve_threshold(explicit, preset_key, default, *, aggressive)`
  encodes the three-state precedence (explicit flag > aggressive preset
  > built-in default) and is the single source of truth, called inside
  the shared `cli._build_repl_loop`. Both REPLs route budget/max-steps
  resolution through that one function, so they cannot drift. The
  `--help` text for both budget flags gained the line "If
  --aggressive-thresholds is also set and you do not pass this flag, the
  preset value applies; otherwise the built-in default applies."
- **design decisions (deviations from PLAN)**:
  - **Resolution placed in `_build_repl_loop`, not "the top of
    `_run_repl`"**: PLAN's prose says resolve at the top of `_run_repl`,
    but the exit-gate matrix strategy says to "construct a loop via
    `cli._build_repl_loop` directly … and assert the expected effective
    value." Those only reconcile if resolution lives in
    `_build_repl_loop`. Placing it there also makes openai_cli inherit
    identical precedence structurally (it already delegates to
    `_build_repl_loop`), so drift is impossible by construction.
    Visible in: `src/simple_coding_agent/cli.py` (`_resolve_threshold`
    + `_build_repl_loop` body). Impact on M3: none — M3 must not touch
    `cli.py` / `openai_cli.py`.
  - **compact.py was NOT modified**: PLAN listed a `MicroCompactor`
    `+3-line guard`, but the guard already exists at
    `compact.py:303-304` (`if threshold_minutes < 1: raise ValueError(
    "threshold_minutes must be >= 1")`) — it already mirrors
    `SnipTool`'s `"keep_recent must be >= 1"`. Only the negative test
    was missing, so M2 added the test and left the source untouched
    (lower-risk; the message already mirrors SnipTool exactly). Impact
    on M3: none.
  - **Reused existing `_DEFAULT_CONTEXT_TOKENS`**: PLAN suggested adding
    `_DEFAULT_MAX_CONTEXT_TOKENS`. cli.py already had
    `_DEFAULT_CONTEXT_TOKENS = 200_000`, `_DEFAULT_RESERVED_OUTPUT_TOKENS
    = 8_192`, `_DEFAULT_MAX_STEPS = 10`, so M2 reused those rather than
    introduce a duplicate constant (DRY). `--max-steps` keeps default 10
    (it has no preset entry; PLAN's "= 50 (if applicable)" was not
    applicable).
- **known limitations**:
  - `openai_cli._DEFAULT_MAX_STEPS` is now dead (it was only the old
    argparse default; max-steps resolution flows through cli's constant
    via `_build_repl_loop`). Left in place to avoid extra churn; safe to
    delete in a future cleanup. Not a regression. ruff/mypy clean.

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `30945de` — `git -C python-replica show HEAD`
  (M1 is at `6284ea8`; the `71d3c80` recorded above was M1's
  pre-rebase sha — git HEAD is the source of truth)
- **tests**: 605 passing (was 584 after `M1`, delta +21)
- **mypy**: clean
- **ruff**: clean
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that `M3` and subsequent milestones MUST respect. Update by
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

Constraints added by `M1`:

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

Constraints added by `M2`:

- **do not modify**:
  - `src/simple_coding_agent/cli.py` and
    `src/simple_coding_agent/openai_cli.py` — M3 is doc/demo/test only
    and must NOT touch either CLI module. Resolution lives in
    `cli._resolve_threshold` + `cli._build_repl_loop`; `openai_cli`
    delegates to it, and the symmetry test
    (`tests/test_openai_cli_repl.py::
    test_openai_repl_aggressive_budget_matches_cli_sentinel`) will fail
    loudly if the two ever diverge.
- **preserve**:
  - The argparse defaults for `--max-context-tokens`,
    `--reserved-output-tokens`, and `--max-steps` are now `None`
    sentinels (both REPLs). The user-visible `--help` text for the two
    budget flags includes the exact phrase `If --aggressive-thresholds
    is also set and you do not pass this flag, the preset value applies;
    otherwise the built-in default applies.` **This exact phrase is
    pinned by M3's `--help` snapshot test** — it currently renders
    contiguously in `--help` (verified). If M3's snapshot fails on it,
    the snapshot is wrong, not cli.py.
- **compatibility requirements**:
  - `MicroCompactor.__init__` rejects `threshold_minutes < 1` with
    `ValueError` (pre-existing guard at `compact.py:303-304`, now
    test-covered). Any future `MicroCompactor(threshold_minutes=...)`
    construction must pass `>= 1`.
  - Non-aggressive default behaviour is unchanged: a plain `--repl`
    (no `--aggressive-thresholds`, no explicit flag) still resolves to
    `200_000` / `8_192` / max-steps `10`. Tests that assume those
    defaults (e.g. `test_cli_max_steps_flag_default_is_10`) stay green.

## 5. Next milestone guidance

For `M3` — demo-fences-zero-overhead-and-doc-sync:

- **next scope**: Zero source-code change — examples / docs / tests
  only. Extend `examples/visibility_full_demo._new_run_dir` to handle
  same-second timestamp collisions by appending a `-2`…`-9` suffix
  (`SystemExit` if all nine are taken in one second). Extend
  `_parse_trace_events` to tolerate the repr-quoted values M1 introduced
  (after `=`, if the next char is `'`/`"`, read to the matching close
  quote; otherwise split on whitespace as before). Add a `NullTracer`
  `timeit` perf assertion (100_000 `emit` calls < 20ms, mean < 200ns;
  skip under coverage via `os.environ.get("COVERAGE_RUN")` or
  `sys.gettrace()`). Add a `--help` snapshot test pinning the key
  phrases for `--verbose`, `--aggressive-thresholds`, and
  `--max-context-tokens` **including the M2-added line** (see Section 4
  "preserve" for the exact wording). Sync `README.md` "Examples" and
  add a `python-replica/CLAUDE.md` "Implementation Roadmap" entry for
  this initiative with the SHA range and pytest delta.
- **relevant files**:
  - `examples/visibility_full_demo.py` — extend `_new_run_dir` and
    `_parse_trace_events` only; do NOT create new example files.
  - `tests/test_visibility_full_demo.py` — directory-collision case +
    parser-tolerates-quoted-values case.
  - `tests/test_trace.py` — add the `NullTracer` perf assertion (coverage
    skip guard).
  - `tests/test_cli.py` — add the `--help` snapshot test.
  - `README.md`, `python-replica/CLAUDE.md` — doc sync.
- **expected tests**: ~10 new cases (directory collision 1-2, parser
  tolerance 2, perf assert 1, --help snapshot 2-3, README reference
  check 1, regression coverage 1-2). pytest 605 → keep the PLAN's
  ≥587 floor with comfortable margin.
- **risks**:
  - **Do NOT touch `cli.py` or `openai_cli.py`.** If the `--help`
    snapshot test fails after you write it, the snapshot wording is
    wrong (M2 pinned the phrase and verified it renders contiguously) —
    investigate the snapshot before editing cli.py.
  - The perf assertion is interpreter-sensitive; the 200ns budget has
    ~2-3× headroom on the harness, and the coverage skip prevents
    false-fails under `pytest --cov`.
  - `_parse_trace_events` already works for scalar lines; only
    whitespace/non-scalar (repr-quoted) values need the new branch —
    preserve backward compatibility for unquoted values.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M3.md`
