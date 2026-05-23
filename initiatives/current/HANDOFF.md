# HANDOFF — Next: M1 (trace-robustness-and-leak-coverage)

> Updated by: Phase 1 bootstrap of `obs-thr-harden`
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `obs-thr-harden`
- **current milestone**: _(not started)_
- **next milestone**: `M1` — trace-robustness-and-leak-coverage
- **all milestones (per PLAN)**: M1 [next], M2 [pending], M3 [pending]

## 2. Completed milestones

_(none yet — this initiative has not started)_

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `e8e2206c2fc6737f509229b2414bb578dc4d99e1` — `git -C python-replica show e8e2206c2fc6737f509229b2414bb578dc4d99e1`
- **tests**: 557 passing
- **mypy**: clean
- **ruff**: clean
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: _(none yet — first milestone has free hand within its scope)_
- **preserve**: _(none yet)_
- **compatibility requirements**: _(none yet)_

Initiative-level invariants from PLAN.md "Anything else" that every
milestone prompt's §2.5 echoes:

- Do not change the 9-channel list (`compact`, `reactive`,
  `microcompact`, `snip`, `externalize`, `memory_select`, `claude_md`,
  `auto_learn`, `budget`).
- Do not add or remove keys from `_AGGRESSIVE_THRESHOLDS` (values may
  be tuned but the 8-key set is frozen).
- Do not change the `NullTracer.emit` body — it must remain literally
  `pass`.
- Do not introduce new dependencies (the perf assertion uses stdlib
  `timeit`; do not add `pytest-benchmark`, `freezegun`, etc.).

## 5. Next milestone guidance

For `M1` — trace-robustness-and-leak-coverage:

- **next scope**: harden `src/simple_coding_agent/trace.py`'s
  `StderrTracer.emit` against (a) closed-stream `OSError` /
  `ValueError` and (b) non-string / whitespace-containing field
  values; expand the secret-leak negative test from 1 shape to >= 4
  (Bearer, AWS, long OpenAI, Unicode); add a reactive-channel
  end-to-end test and a whitespace-roundtrip test for the demo
  parser contract. Single src file (`trace.py`) + single test file
  (`tests/test_trace.py`). See `initiatives/current/PLAN.md` and
  `initiatives/current/config.yaml` for the authoritative scope.
- **relevant files**:
  - `src/simple_coding_agent/trace.py` — the only src file edited
  - `tests/test_trace.py` — all new tests land here
  - `tests/test_stress_full_compact.py` — read-only reference for
    the existing MockProvider + `PromptTooLongError` fixture pattern
    (reuse it for the reactive end-to-end test)
  - `examples/visibility_full_demo.py` — read-only; do NOT edit in
    M1, but understand `_parse_trace_events` so the whitespace
    roundtrip test correctly proves the contract M3 will extend.
- **expected tests**: extend `tests/test_trace.py` with ~8 new cases
  (see PLAN.md `notes` for the M1 breakdown).
- **risks**: M1 has no prior-milestone risks to inherit. The most
  likely landmine is wording the closed-stream guard so it does NOT
  swallow `KeyboardInterrupt` / `SystemExit` — catch only
  `(OSError, ValueError)`. The `_render_value` helper must keep the
  trace line ASCII; using `repr()` (not `json.dumps`) is the simplest
  way to do that.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M1.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
