# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**ctx-mgmt-pdf-align** — see
[`initiatives/current/`](./initiatives/current/).

| | |
|---|---|
| Bootstrapped | 2026-05-23 |
| Milestones | M1 → M4 |
| Baseline commit | `8f1d98f` |
| Baseline pytest | 615 passing |
| Status | Bootstrapped, awaiting Phase 2 execution |

Goal: align the 5-mechanism context-management pipeline with Claude
Code v2.1.88's behaviour per the user's `claude_code_notes.pdf` rubric.
Closes every gap except forked-agent + prompt-cache sharing.

Next command:

```
./automation/scripts/run_all_milestones.sh
```

## Last completed initiative

**obs-thr-harden** — see
[`initiatives/_archive/2026-05-obs-thr-harden/`](./initiatives/_archive/2026-05-obs-thr-harden/).

| | |
|---|---|
| Period | 2026-05-23–2026-05-23 |
| Milestones | M1 → M3 |
| Final commit | `4582997` |
| pytest | 557 → 615 (+58) |
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
