<!--
SKELETON for the handoff file rewritten by each milestone at its exit
ritual (step 4 of §5 in automation/templates/milestone_prompt.md).
The milestone agent overwrites initiatives/current/HANDOFF.md with a
filled-in copy of this file every time it completes.
Section 3 is the most important: be specific about divergences so the
next milestone can decide whether to inherit or revert.
-->

# HANDOFF — Next: {{NEXT_MILESTONE_ID}} ({{NEXT_MILESTONE_NAME}})

> Updated by: {{JUST_COMPLETED_MILESTONE_ID}} session
> Date: {{TODAY}}
> Read this file FIRST in the next session, then verify against git/pytest.

---

## 1. Objective State

> The next session MUST re-verify these numbers. Do not trust this list
> blindly — re-run the commands.

- Last commit: `{{COMMIT_SHA}}` — `git -C python-replica show {{COMMIT_SHA}}` to inspect
- pytest: {{PYTEST_COUNT}} passing (was {{PREV_PYTEST_COUNT}} after {{PREV_MILESTONE_ID}}, delta {{PYTEST_DELTA}})
- mypy:   {{MYPY_STATUS}}
- ruff:   {{RUFF_STATUS}}
- Branch: {{BRANCH}}

## 2. What {{JUST_COMPLETED_MILESTONE_ID}} accomplished

- {{PHASE_ID_1}}: <what shipped, in one bullet>
- {{PHASE_ID_2}}: <what shipped, in one bullet>
- Test additions: `tests/test_xxx.py` (+N cases), `tests/test_yyy.py` (+M cases). Total: {{PREV_PYTEST_COUNT}} → {{PYTEST_COUNT}}.

## 3. Decisions Made That Diverge From Plan ⚠️

> THE MOST IMPORTANT SECTION. Any place reality diverged from
> `initiatives/current/PLAN.md` — alternative library, skipped test,
> renamed function, added abstraction, deferred work, etc. Include
> the WHY so the next session can decide whether to inherit or revert.

- **<short title of divergence>**: <what was different from plan and
  why>. <Where in the diff it is visible>. <Impact on next milestone>.
- (none) if truly no divergences

## 4. Open Questions / Blockers for {{NEXT_MILESTONE_ID}}

> Anything needing human input, or pre-conditions for {{NEXT_MILESTONE_ID}}.
> If none, write "(none)".

(none) — all quality gates green; working tree clean before this handoff
was written.

## 5. Next Session Prompt

> The autonomous loop (`automation/scripts/run_all_milestones.sh`) does
> NOT read this section — it reads `initiatives/current/prompts/{{NEXT_MILESTONE_ID}}.md`
> directly. This section exists only for manual single-milestone restarts
> via `automation/scripts/run_next.sh`.

See `initiatives/current/prompts/{{NEXT_MILESTONE_ID}}.md` for the full
prompt the loop will feed to the next session.
