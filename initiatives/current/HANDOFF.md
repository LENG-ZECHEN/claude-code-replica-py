# HANDOFF — Next: M1 (trace-hooks-and-verbose-flag)

> Updated by: Phase 1 bootstrap of `observable-thresholds`
> Date: 2026-05-22
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `observable-thresholds`
- **current milestone**: _(not started)_
- **next milestone**: `M1` — trace-hooks-and-verbose-flag
- **all milestones (per PLAN)**: M1 [next], M2 [pending], M3 [pending]

  <!-- format: "M1 [next], M2 [pending], M3 [pending]" -->

## 2. Completed milestones

_(none yet — this initiative has not started)_

<!--
After each milestone, the milestone agent APPENDS one subsection like:

### {{MILESTONE_ID}}

- **commit**: `<sha>` `[<commit_prefix>/{{MILESTONE_ID}}] <subject>`
- **files changed**: `<file1>`, `<file2>`, ...
- **tests added**: `<test_file>` (+N cases). Total: <before> -> <after>
- **behavior implemented**: <one-paragraph factual summary — what now
  works that did not before. Cite new public symbols / CLI flags /
  slash commands.>
- **design decisions (deviations from PLAN)**:
  - `<short title>`: <what was different and WHY>. Visible in:
    `<path:line>`. Impact on next milestone: <e.g., "must respect new
    invariant X">.
  - (none) if truly no divergences
- **known limitations**:
  - <thing not fully done; e.g., "happy-path only, error case deferred">
  - (none) if you fully cleaned up

Prior subsections are NEVER deleted or rewritten — each milestone is the
source of truth on itself.
-->

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `2d414d91da65cc5998563e9c63b2d2be7028315d` — `git -C python-replica show 2d414d91da65cc5998563e9c63b2d2be7028315d`
- **tests**: 520 passing
- **mypy**: clean (no issues found in 20 source files)
- **ruff**: clean (all checks passed)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: _(none yet — first milestone has free hand within its scope)_
- **preserve**: _(none yet)_
- **compatibility requirements**: _(none yet)_

## 5. Next milestone guidance

For `M1` — trace-hooks-and-verbose-flag:

- **next scope**: see `initiatives/current/PLAN.md` and
  `initiatives/current/config.yaml` for the authoritative scope.
- **relevant files**: M1 starts on a clean baseline. Consult PLAN.md
  for expected affected modules and `initiatives/current/prompts/M1.md`
  §2 "Expected files to touch" once Phase 1 finishes generating prompts.
- **expected tests**: see PLAN.md "Detailed Test Plan" (if present) and
  the milestone-specific notes in config.yaml.
- **risks**: M1 has no prior-milestone risks to inherit. Consult
  PLAN.md "Risks / known unknowns" section.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M1.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
