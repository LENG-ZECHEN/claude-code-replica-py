# HANDOFF — Initiative complete (M3 was the last milestone)

> Updated by: `M3` session
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `obs-thr-harden`
- **current milestone**: just-completed `M3` — demo-fences-zero-overhead-and-doc-sync
- **next milestone**: none — initiative complete
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done]

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

### M3

- **commit**: `9b00767` `[obs-thr-hd/M3] demo collision fences + NullTracer perf assert + doc sync` (HEAD is source of truth; sha recorded pre-amend)
- **files changed**: `examples/visibility_full_demo.py`,
  `tests/test_visibility_full_demo.py`, `tests/test_trace.py`,
  `tests/test_cli.py`, `README.md`, `CLAUDE.md` (plus the three
  initiative bookkeeping files: `PROGRESS.md`, `HANDOFF.md`, `PLAN.md`)
- **tests added**: `tests/test_visibility_full_demo.py` (+7 — 3
  `_new_run_dir` collision cases: base-when-free, `-2`/`-3` suffix on
  collision, `SystemExit` when all 9 are taken; 4 `_parse_trace_events`
  cases: unquoted backward-compat, quoted-whitespace, dict repr, list
  repr), `tests/test_trace.py` (+1 — `test_null_tracer_zero_overhead`
  timeit assertion, coverage-skipped), `tests/test_cli.py` (+2 —
  `--help` snapshot pins flag phrases + the `preset value applies`
  precedence line). Total: 605 → 615 (+10).
- **behavior implemented**: `examples/visibility_full_demo._new_run_dir`
  no longer clobbers a prior run that started in the same wall-clock
  second — it appends a `-2` … `-9` suffix to the timestamped
  directory name and raises `SystemExit` with a clear message if all
  nine are taken in one second (was `mkdir(exist_ok=True)`, which
  silently shared one directory). `_parse_trace_events` now tolerates
  the repr-quoted values M1 introduced: a new module-level `_scan_value`
  helper reads quoted strings to their closing quote and bracketed
  reprs (`{...}` / `[...]` / `(...)`) to their balanced close, so a
  space-containing value can no longer shred the adjacent `k=v` field;
  unquoted scalar lines parse exactly as before. `NullTracer`'s
  zero-overhead promise is now pinned by a `timeit` assertion (100_000
  `emit` calls < 20ms, mean < 200ns/call), skipped under coverage /
  trace instrumentation. A `--help` snapshot test pins the
  `--verbose` / `--aggressive-thresholds` / `--max-context-tokens` flag
  phrasing and, critically, the exact M2 wording `preset value applies`,
  so future help-text drift cannot silently drop the precedence note.
  README gained an "## Examples" section + the previously-missing
  `aggressive_thresholds_demo.py` / `stress_demo.py` /
  `microcompact_demo.py` entries; CLAUDE.md gained the roadmap bullet
  for this initiative.
- **design decisions (deviations from PLAN)**:
  - **`_scan_value` also handles bracket-delimited reprs, not only
    quote-delimited values**: PLAN's prose for `_parse_trace_events`
    says "if the next character is `'` or `\"`, read until the matching
    closing quote." But the exit gate explicitly requires tolerating
    "dict / list reprs," and `repr({...})` starts with `{`, not a quote.
    So `_scan_value` reads quote-, brace-, bracket-, and paren-delimited
    values whole (balanced, quote-aware). This is a superset of PLAN's
    rule and is required to satisfy the gate; backward compatibility for
    unquoted scalars is preserved. Visible in:
    `examples/visibility_full_demo.py` (`_scan_value` / `_parse_fields`).
    Impact on a follow-up: none — internal to the demo.
  - **`--help` snapshot normalizes whitespace before matching**: the
    verbose help renders as ``Stream `[trace] [<channel>] …`` (with a
    backtick), so the PLAN's suggested literal `"Stream [trace]"` is not
    a contiguous substring. The test collapses whitespace runs and pins
    phrases that genuinely appear (`[trace]`, `lines to stderr`,
    `preset value applies`), which is more robust to argparse line-wrap
    than a raw-block snapshot. The M2-pinned phrase is matched exactly.
- **known limitations**:
  - The recorded commit sha `9b00767` is substituted post-commit and
    then folded in via `git commit --amend`, so the value written here
    is one amend-generation behind the final HEAD (same convention M1's
    `71d3c80` followed). `git -C python-replica log -1` is authoritative.

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `9b00767` — `git -C python-replica log --oneline -1`
  (HEAD is the source of truth; the recorded sha is pre-amend)
- **tests**: 615 passing (was 605 after `M2`, delta +10)
- **mypy**: clean
- **ruff**: clean
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that follow-up initiatives MUST respect. Update by ADDING —
> only remove a constraint by quoting it and explaining why it is retired.

Initiative-level invariants from PLAN.md "Anything else" (still in force):

- Do not change the 9-channel list (`compact`, `reactive`,
  `microcompact`, `snip`, `externalize`, `memory_select`, `claude_md`,
  `auto_learn`, `budget`).
- Do not add or remove keys from `_AGGRESSIVE_THRESHOLDS` (values may be
  tuned but the 8-key set is frozen).
- Do not change the `NullTracer.emit` body — it must remain literally
  `pass`. **This is now load-bearing**: `test_null_tracer_zero_overhead`
  (M3) asserts 100k `emit` calls complete in < 20ms, which only holds
  while the body does no work.
- Do not introduce new dependencies (M3's perf assertion uses stdlib
  `timeit`; do not add `pytest-benchmark`, `freezegun`, etc.).

Constraints added by `M1`:

- **do not modify**:
  - `StderrTracer.emit` MUST keep the `(OSError, ValueError)` guard on
    the `write` call (`src/simple_coding_agent/trace.py`). Removing it
    re-introduces the closed-stream crash that M1 fixed. Do not widen it
    to bare `except Exception:` — `KeyboardInterrupt`/`SystemExit` must
    propagate.
- **preserve**:
  - `_render_value` helper in `trace.py` is part of the internal
    interface that M3's demo-parser tolerance work depends on. Do not
    rename it or change its semantics without coordinating with
    `visibility_full_demo._parse_trace_events`, which reads the
    repr-quoted form it produces.
- **compatibility requirements**:
  - The locked scalar line format `[trace] [<channel>] k=v ...` is
    byte-identical for scalar values (regression-pinned by
    `test_nine_channel_format_unchanged_for_scalar_values`). Only
    whitespace/non-scalar values gained repr-quoting.

Constraints added by `M2`:

- **do not modify**:
  - `src/simple_coding_agent/cli.py` and
    `src/simple_coding_agent/openai_cli.py` — resolution lives in
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
    otherwise the built-in default applies.` **This exact phrase is now
    pinned by M3's `--help` snapshot test** — it renders contiguously in
    `--help`. If that snapshot ever fails, the snapshot is wrong, not
    cli.py.
- **compatibility requirements**:
  - `MicroCompactor.__init__` rejects `threshold_minutes < 1` with
    `ValueError` (pre-existing guard at `compact.py:303-304`, now
    test-covered). Any future `MicroCompactor(threshold_minutes=...)`
    construction must pass `>= 1`.
  - Non-aggressive default behaviour is unchanged: a plain `--repl`
    (no `--aggressive-thresholds`, no explicit flag) still resolves to
    `200_000` / `8_192` / max-steps `10`.

Constraints added by `M3`:

- **preserve**:
  - The pinned `--help` wording `preset value applies` (M2) is now
    load-bearing — both `cli.py` and the `tests/test_cli.py` snapshot
    test depend on it. Reword the help only if you update the snapshot
    in the same change.
  - `visibility_full_demo._parse_trace_events` now accepts both unquoted
    and `'`/`"`-quoted (and `{`/`[`/`(`-bracketed) values. Future changes
    to the trace line shape must keep one of these forms parseable.
- **compatibility requirements**:
  - `examples/visibility_full_demo._new_run_dir` returns a unique
    directory or raises `SystemExit`; it never overwrites an existing
    run directory. Callers must tolerate the `-2`…`-9` suffix in the
    returned path name.

## 5. Next milestone guidance

_(initiative complete — follow-up initiatives bootstrap from a fresh INBOX.md)_
