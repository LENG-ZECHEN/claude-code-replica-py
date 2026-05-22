<!--
SKELETON for the handoff file rewritten by each milestone at its exit
ritual (step 4 of §5 in automation/templates/milestone_prompt.md).

The milestone agent overwrites initiatives/current/HANDOFF.md with a
filled-in copy of this file every time it completes.

The 5-section structure (Current initiative / Completed milestones /
Current repo state / Important constraints / Next milestone guidance)
is non-negotiable and identical to handoff_initial.md.

In Section 2, the milestone agent APPENDS its own subsection to whatever
subsections prior milestones left. NEVER delete or rewrite a prior
milestone's subsection — each milestone is the source of truth on itself.

In Section 4, the milestone agent APPENDS new constraints (do-not-modify,
preserve, compatibility). Entries are removed only when explicitly retired
by a later milestone that quotes the original constraint and explains why
it no longer applies.

Comment blocks (HTML comments) are guidance to the milestone agent and
should NOT appear in the written HANDOFF.md.
-->

# HANDOFF — Next: {{NEXT_MILESTONE_ID}} ({{NEXT_MILESTONE_NAME}})

> Updated by: `{{JUST_COMPLETED_MILESTONE_ID}}` session
> Date: {{TODAY}}
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `{{INITIATIVE_SLUG}}`
- **current milestone**: just-completed `{{JUST_COMPLETED_MILESTONE_ID}}` — {{JUST_COMPLETED_MILESTONE_NAME}}
- **next milestone**: `{{NEXT_MILESTONE_ID}}` — {{NEXT_MILESTONE_NAME}}
- **all milestones (per PLAN)**: {{ALL_MILESTONE_IDS_WITH_STATUS}}

  <!-- format: "M1 [done], M2 [done], M3 [next], M4 [pending], M5 [pending]" -->

## 2. Completed milestones

<!--
PRESERVE every prior subsection verbatim. APPEND your own subsection at
the bottom. Each subsection's fields are all required (use "(none)" for
empty ones).
-->

{{PRIOR_MILESTONE_BLOCKS}}

### {{JUST_COMPLETED_MILESTONE_ID}}

- **commit**: `{{COMMIT_SHA}}` `[{{COMMIT_PREFIX}}/{{JUST_COMPLETED_MILESTONE_ID}}] {{COMMIT_SUBJECT}}`
- **files changed**: `<file1>`, `<file2>`, ...
- **tests added**: `<test_file>` (+N cases). Total: {{PREV_PYTEST_COUNT}} → {{PYTEST_COUNT}}
- **behavior implemented**: <one-paragraph factual summary — what now
  works that did not before. Cite new public symbols / CLI flags /
  slash commands / env vars.>
- **design decisions (deviations from PLAN)**:
  - **<short title>**: <what was different from PLAN and WHY>. Visible
    in: `<path:line>`. Impact on `{{NEXT_MILESTONE_ID}}`: <e.g., "must
    respect new invariant Z" / "can ignore — internal only">.
  - (none) if truly no divergences
- **known limitations**:
  - <thing not fully done; e.g., "happy-path only, error case deferred to M4">
  - (none) if you fully cleaned up

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `{{COMMIT_SHA}}` — `git -C python-replica show {{COMMIT_SHA}}`
- **tests**: {{PYTEST_COUNT}} passing (was {{PREV_PYTEST_COUNT}} after `{{PREV_MILESTONE_ID}}`, delta +{{PYTEST_DELTA}})
- **mypy**: {{MYPY_STATUS}}
- **ruff**: {{RUFF_STATUS}}
- **branch**: {{BRANCH}}
- **known failing checks**: none | <list any quarantined / xfail tests>

## 4. Important constraints (carried forward)

> Invariants that `{{NEXT_MILESTONE_ID}}` and subsequent milestones MUST
> respect. Update by ADDING — only remove a constraint by quoting it
> and explaining why it is retired.

{{PRIOR_CONSTRAINTS}}

<!-- New constraints from {{JUST_COMPLETED_MILESTONE_ID}}, if any: -->

- **do not modify**:
  - `<path>` — <reason; e.g., "frozen by {{JUST_COMPLETED_MILESTONE_ID}} design decision: new public API">
  - (none) if no new freezes
- **preserve**:
  - `<test or behavior>` — <reason>
  - (none)
- **compatibility requirements**:
  - <e.g., "the new XClient.connect() signature is part of public API; do not change it">
  - (none)

## 5. Next milestone guidance

For `{{NEXT_MILESTONE_ID}}` — {{NEXT_MILESTONE_NAME}}:

- **next scope**: <2-3 sentences. Paraphrase from PLAN.md / config.yaml,
  but add anything you learned in `{{JUST_COMPLETED_MILESTONE_ID}}` that
  sharpens the next milestone's job.>
- **relevant files**:
  - `<src/path/x.py>` — <why; e.g., "extends what {{JUST_COMPLETED_MILESTONE_ID}} introduced">
  - `<tests/path/test_y.py>` — <why>
- **expected tests**:
  - `<tests/test_<thing>.py>` — <what to cover (happy path + at least one error/edge case)>
- **risks**:
  - <surprise you ran into in `{{JUST_COMPLETED_MILESTONE_ID}}`;
    e.g., "the new XClient call sometimes hangs on bad input — make sure
    `{{NEXT_MILESTONE_ID}}` handles that case">
  - (none) if smooth sailing

The full ready-to-run prompt is at:
`initiatives/current/prompts/{{NEXT_MILESTONE_ID}}.md`

{{IF_LAST_MILESTONE_BLOCK}}
