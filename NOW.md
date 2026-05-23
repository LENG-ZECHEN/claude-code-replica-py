# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**obs-thr-harden** — see
[`initiatives/current/`](./initiatives/current/).

| | |
|---|---|
| Slug | `obs-thr-harden` |
| Started | 2026-05-23 |
| Milestones | M1 → M3 (3 total) |
| Status | bootstrapped (Phase 1 complete; M1 pending) |
| Baseline commit | `e8e2206c2fc6737f509229b2414bb578dc4d99e1` |
| Baseline pytest | 557 passing |
| Target pytest | M1 >= 565, M2 >= 577, M3 >= 587 |
| Goal | Hardening pass over `observable-thresholds` (M1+M2+M3): fix the `_AGGRESSIVE_THRESHOLDS` preset bug, expand precedence + leak coverage, add demo collision fences, pin NullTracer zero-overhead. |

Next action: run `./automation/scripts/run_all_milestones.sh` from the
`python-replica/` directory to execute Phase 2 (M1 → M2 → M3 → review).

## Last completed initiative

**observable-thresholds** — see
[`initiatives/_archive/2026-05-observable-thresholds/`](./initiatives/_archive/2026-05-observable-thresholds/).

| | |
|---|---|
| Period | 2026-05-22 – 2026-05-23 |
| Milestones | M1 → M3 |
| Final commit | `026db2e` |
| pytest | 520 → 557 (+37) |
| mypy + ruff | clean |

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
