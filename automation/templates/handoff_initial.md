<!--
SKELETON for the FIRST handoff file in a new initiative.
Phase 1 (RUNBOOK Step 6) instantiates this as
initiatives/current/HANDOFF.md right after Phase 1 Steps 1-5.
At this point no milestone has run, so Section 2 is empty and
Section 3 declares "no divergences yet".
The first milestone (M1) overwrites this file using
automation/templates/handoff_milestone.md at its exit ritual.
-->

# HANDOFF — Next: {{FIRST_MILESTONE_ID}} ({{FIRST_MILESTONE_NAME}})

> Updated by: Phase 1 bootstrap of `{{INITIATIVE_SLUG}}`
> Date: {{TODAY}}
> Read this file FIRST in the next session, then verify against git/pytest.

---

## 1. Objective State (BASELINE — verify before any code change)

- Last commit: `{{BASELINE_COMMIT}}` — `git -C python-replica show {{BASELINE_COMMIT}}` to inspect
- pytest: {{BASELINE_PYTEST}} passing
- mypy:   {{BASELINE_MYPY}}
- ruff:   {{BASELINE_RUFF}}
- Branch: {{BASELINE_BRANCH}}

## 2. What previous milestone accomplished

_(none — this initiative has not started a milestone yet)_

## 3. Decisions Made That Diverge From Plan ⚠️

> THE MOST IMPORTANT SECTION. Any place reality diverged from
> `initiatives/current/PLAN.md` — alternative library, skipped test,
> renamed function, added abstraction, deferred work, etc.
> The next milestone session reads this first.

_(none yet)_

## 4. Open Questions / Blockers for {{FIRST_MILESTONE_ID}}

> Anything needing human input, or pre-conditions for the first milestone.
> If none, write "(none)".

(none — Phase 1 bootstrap has just completed; M1 can start cleanly.)

## 5. Next Session Prompt

> The autonomous loop (`automation/scripts/run_all_milestones.sh`) does
> NOT read this section — it reads `initiatives/current/prompts/{{FIRST_MILESTONE_ID}}.md`
> directly. This section exists only for manual single-milestone restarts
> via `automation/scripts/run_next.sh`.

See `initiatives/current/prompts/{{FIRST_MILESTONE_ID}}.md` for the full
prompt that will be fed to the next session.
