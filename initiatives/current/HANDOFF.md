# HANDOFF — Next: M1 (cli-flags-microcompact-minutes-and-max-turns)

> Updated by: Phase 1 bootstrap of `ctx-mgmt-demo`
> Date: 2026-05-25
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-demo`
- **current milestone**: _(not started)_
- **next milestone**: `M1` — cli-flags-microcompact-minutes-and-max-turns
- **all milestones (per PLAN)**: M1 [next], M2 [pending], M3 [pending]

## 2. Completed milestones

_(none yet — this initiative has not started)_

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `9ba662bf65e45d08949d4524203773a63bf36902` — `git -C python-replica show 9ba662b`
- **tests**: 816 passing
- **mypy**: clean (no issues in 26 source files)
- **ruff**: clean
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: _(none yet — first milestone has free hand within its scope)_
- **preserve**: _(none yet)_
- **compatibility requirements**: _(none yet)_

## 5. Next milestone guidance

For `M1` — cli-flags-microcompact-minutes-and-max-turns:

- **next scope**: two additive CLI flags. `--microcompact-minutes N`
  on both `cli.py` and `openai_cli.py` (plumb to
  `MicroCompactor(threshold_minutes=N)` via the existing
  `cli._resolve_threshold` three-state precedence). `--max-turns N`
  on `openai_cli.py` REPL only (counter in the read loop;
  shutdown via the same path as `/exit`). See
  `initiatives/current/PLAN.md` and
  `initiatives/current/config.yaml` for the authoritative scope.
- **relevant files**: `src/simple_coding_agent/cli.py`,
  `src/simple_coding_agent/openai_cli.py`. `MicroCompactor` in
  `compact.py` already accepts `threshold_minutes`; no src change
  expected there.
- **expected tests**: at least 3 new cases across `tests/test_cli.py`
  and `tests/test_openai_cli.py` (or `test_openai_cli_repl.py`).
- **risks**: `--microcompact-minutes 0` may trip the existing
  `MicroCompactor(threshold_minutes<1)` guard test from
  `observable-thresholds-harden M2`. Check that guard first and
  either relax it to `N<0` or change the flag minimum to 1 (and
  flag the M2 capture scenario 03 to use 1 + brief sleep).

The full ready-to-run prompt is at:
`initiatives/current/prompts/M1.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
