<!--
SKELETON for initiatives/current/PROGRESS.md.

Phase 1 Step 7 (RUNBOOK) writes the header at the top of this file as
the initial PROGRESS.md (no entries yet).

Each milestone agent at exit ritual step 3 APPENDS one "## M{N} — done
<YYYY-MM-DD>" block to the bottom of PROGRESS.md, formatted exactly
like the example block below.
-->

# {{INITIATIVE_SLUG}} progress log

Cumulative milestone log for the {{INITIATIVE_SLUG}} initiative.
Append one block per milestone, newest at the bottom.

<!-- BEGIN example block — copy + customize this for every milestone -->

## {{MILESTONE_ID}} — done {{TODAY}}

Phase {{PHASE_IDS}}. <one-paragraph factual summary of what shipped:
new file(s), new flag(s), new symbol(s). Include the commit subject
verbatim if it helps disambiguate. End with the pytest delta and what
the next milestone should pick up.>

Files: `<file1>`, `<file2>` (+N tests in `<test_files>`).
Commit: `<sha> [<commit_prefix>/{{MILESTONE_ID}}] <subject>`.
pytest {{PREV_COUNT}} → {{NEW_COUNT}} (+{{DELTA}}). mypy + ruff clean.
{{NEXT_MILESTONE_ID}} should pick up phase {{NEXT_PHASE_IDS}} per
initiatives/current/PLAN.md.

<!-- END example block -->
