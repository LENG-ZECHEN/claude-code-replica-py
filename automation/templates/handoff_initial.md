<!--
SKELETON for the FIRST handoff file in a new initiative.
Phase 1 (RUNBOOK Step 6) instantiates this as
initiatives/current/HANDOFF.md right after Phase 1 Steps 1-5.

At this point no milestone has run, so Section 2 is empty (a placeholder
note) and Section 4 has "(none yet)" entries.

The first milestone (M1) overwrites this file using
automation/templates/handoff_milestone.md at its exit ritual.

The 5-section structure (Current initiative / Completed milestones /
Current repo state / Important constraints / Next milestone guidance)
is non-negotiable. Each milestone's overwrite preserves the same shape.
-->

# HANDOFF — Next: {{FIRST_MILESTONE_ID}} ({{FIRST_MILESTONE_NAME}})

> Updated by: Phase 1 bootstrap of `{{INITIATIVE_SLUG}}`
> Date: {{TODAY}}
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `{{INITIATIVE_SLUG}}`
- **current milestone**: _(not started)_
- **next milestone**: `{{FIRST_MILESTONE_ID}}` — {{FIRST_MILESTONE_NAME}}
- **all milestones (per PLAN)**: {{ALL_MILESTONE_IDS_WITH_STATUS}}

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

- **last commit**: `{{BASELINE_COMMIT}}` — `git -C python-replica show {{BASELINE_COMMIT}}`
- **tests**: {{BASELINE_PYTEST}} passing
- **mypy**: {{BASELINE_MYPY}}
- **ruff**: {{BASELINE_RUFF}}
- **branch**: {{BASELINE_BRANCH}}
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: _(none yet — first milestone has free hand within its scope)_
- **preserve**: _(none yet)_
- **compatibility requirements**: _(none yet)_

## 5. Next milestone guidance

For `{{FIRST_MILESTONE_ID}}` — {{FIRST_MILESTONE_NAME}}:

- **next scope**: see `initiatives/current/PLAN.md` and
  `initiatives/current/config.yaml` for the authoritative scope.
- **relevant files**: M1 starts on a clean baseline. Consult PLAN.md
  for expected affected modules and `initiatives/current/prompts/{{FIRST_MILESTONE_ID}}.md`
  §2 "Expected files to touch" once Phase 1 finishes generating prompts.
- **expected tests**: see PLAN.md "Detailed Test Plan" (if present) and
  the milestone-specific notes in config.yaml.
- **risks**: M1 has no prior-milestone risks to inherit. Consult
  PLAN.md "Risks / known unknowns" section (if you wrote one in INBOX).

The full ready-to-run prompt is at:
`initiatives/current/prompts/{{FIRST_MILESTONE_ID}}.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
