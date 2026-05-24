# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**None.**

`initiatives/current/` is empty (`.gitkeep` only).

## Last completed initiative

**auto-memory-overhaul** — see
[`initiatives/_archive/2026-05-auto-memory-overhaul/`](./initiatives/_archive/2026-05-auto-memory-overhaul/).

| | |
|---|---|
| Period | 2026-05-24 – 2026-05-24 |
| Milestones | M1 → M7 |
| Final commit | `e9aef6a` |
| pytest | 711 → 807 (+96) |
| mypy + ruff | clean |
| English review | [`REVIEW.md`](./initiatives/_archive/2026-05-auto-memory-overhaul/REVIEW.md) |
| Owner brief 中文 | [`OWNER_BRIEF.zh-CN.md`](./initiatives/_archive/2026-05-auto-memory-overhaul/OWNER_BRIEF.zh-CN.md) |

## How to start a new initiative

1. Discuss direction with the agent (free-form chat).
2. Capture the brief in [`automation/INBOX.md`](./automation/INBOX.md)
   (YAML front-matter + free-form markdown — see template inside).
3. Say to any agent session: **"Run RUNBOOK Phase 1."**
4. Agent will bootstrap `initiatives/current/`, pre-write all milestone
   prompts, update this file, and report back. Review the report.
5. Run `./automation/scripts/run_all_milestones.sh`. The script executes
   every milestone and then auto-invokes the review + wrap-up agent.

Full procedure: [`automation/RUNBOOK.md`](./automation/RUNBOOK.md).
