# HANDOFF — Next: M{NEXT}

> Updated by: M{COMPLETED} session
> Date: {YYYY-MM-DD}
> Read this file FIRST in the next session, then verify against git/pytest.

---

## 1. Objective State

> The next session MUST re-verify these numbers. Do not trust this list
> blindly — re-run the commands.

- Last commit: `{HASH}` — `git show {HASH}` to inspect
- pytest: {COUNT} passing (was {PREV}, delta +{DELTA})
- mypy:   clean | {ERRORS}
- ruff:   clean | {ERRORS}
- Branch: {BRANCH}

## 2. What M{COMPLETED} Accomplished

<!-- One bullet per task. Format: <task-id>: <what>. Commit `<hash>`. -->

- {TASK_ID}: {DESCRIPTION}. Commit `{HASH}`.

## 3. Decisions Made That Diverge From Plan ⚠️

> THE MOST IMPORTANT SECTION. Any place reality diverged from
> RUNTIME_ACTIVATION_PLAN.md — alternative library, skipped test,
> renamed function, added abstraction, deferred work, etc. Include
> the WHY so the next session can decide whether to inherit or revert.
>
> If nothing diverged, write "(none)" — do NOT delete the section.

- {DECISION}

## 4. Open Questions / Blockers for M{NEXT}

> Anything needing human input, or pre-conditions for M{NEXT}.
> If none, write "(none)".

- {QUESTION_OR_BLOCKER}

## 5. Next Session Prompt

> Paste the content of the fenced block below into a fresh `claude`
> session opened from `python-replica/`. The prompt is self-contained;
> the next session needs nothing from the current conversation.

```
I'm continuing work on simple_coding_agent, a Python replica of Claude
Code v2.1.88's context-management and memory pipeline.

Before doing anything:
1. Read CLAUDE.md (architecture + completed P-roadmap).
2. Read RUNTIME_ACTIVATION_PLAN.md
     - Section 4 for milestone M{NEXT}'s scope
     - Section 5 for execution rules
3. Read HANDOFF.md — pay close attention to Section 3
   "Decisions Made That Diverge From Plan".
4. Run `git log --oneline -10` and `pytest --tb=no -q` to confirm
   the baseline matches HANDOFF.md Section 1.

Then execute Milestone M{NEXT} only:
  - {PHASE_IDS}    (from RUNTIME_ACTIVATION_PLAN.md Section 2)

Follow Section 5 "Execution Rules" in RUNTIME_ACTIVATION_PLAN.md
strictly. The exact test case lists are in plan Section 3.{N}.

Out of scope: any other milestone. Do NOT touch out-of-milestone code.

Exit ritual for this session (MANDATORY — do all five before stopping):
  1. Milestone M{NEXT}'s exit gate (per plan Section 4) is met.
  2. `git commit -m "P9-M{NEXT}: <one-line>"` has landed.
  3. CLAUDE.md updated with a P9-M{NEXT} entry mirroring P1-P8 format.
  4. PROGRESS.md appended with a one-line summary
     (create the file if it does not exist yet).
  5. HANDOFF.md overwritten using templates/handoff_template.md, with
     all placeholders filled, to hand off to the M{NEXT+1} session.

Confirm you've read all three files (CLAUDE.md, RUNTIME_ACTIVATION_PLAN.md,
HANDOFF.md), then ask me to approve before starting implementation.
```
