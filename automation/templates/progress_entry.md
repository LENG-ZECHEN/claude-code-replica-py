<!--
SKELETON for initiatives/current/PROGRESS.md.

Phase 1 Step 7 (RUNBOOK) writes the header at the top of this file as
the initial PROGRESS.md (no entries yet).

Each milestone agent at exit ritual step 3 APPENDS one block to the
bottom of PROGRESS.md, formatted exactly like the example block below.

PROGRESS.md is a TERSE FACT LOG for the final review session to audit.
Narrative belongs in HANDOFF.md Section 2 ("behavior implemented",
"design decisions"); here you only need the bullets below.

Rule of thumb (per RUNBOOK responsibility split):
  HANDOFF.md  = the cross-milestone state baton (rewritten each milestone)
  PROGRESS.md = the cross-milestone fact log    (append-only, terse)
-->

# {{INITIATIVE_SLUG}} progress log

Cumulative milestone log for the `{{INITIATIVE_SLUG}}` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[<prefix>/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

<!-- BEGIN example block — for shape reference only. The first real
     milestone replaces this with its own block. -->

## {{MILESTONE_ID}} — done {{TODAY}}

- **commit**: `{{COMMIT_SHA}}` `[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}] {{COMMIT_SUBJECT}}`
- **tests**: {{PREV_COUNT}} → {{NEW_COUNT}} (+{{DELTA}})
- **mypy**: {{MYPY_STATUS}} | **ruff**: {{RUFF_STATUS}}
- **files changed**: `<file1>`, `<file2>`, ...
- **exit gate**: `<gate text from §2 of the milestone prompt>` → PASS (<one-line evidence>)
- **notes**: <optional, ≤1 line. Anything longer goes in HANDOFF.md.>

<!-- END example block -->
