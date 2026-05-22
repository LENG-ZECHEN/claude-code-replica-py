# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**Observable Thresholds** — see
[`initiatives/current/`](./initiatives/current/).

| | |
|---|---|
| Slug | `observable-thresholds` |
| Bootstrapped | 2026-05-22 |
| Baseline commit | `2d414d9` |
| Baseline pytest | 520 passing |
| Milestones | M1 → M3 |
| Planned exit | pytest >= 550, `examples/visibility_full_demo.py` produces four artifacts under `--confirm-api-call` |
| Next command | `./automation/scripts/run_all_milestones.sh` |

**Goal.** Make the context-management subsystem (full-compact,
micro-compact, snip, reactive-compact, tool-result externalize) and
the memory subsystem (SessionMemory, ProjectMemory, MemorySelector,
ClaudeMdLoader, auto-learn cue) visible in real time via a `--verbose`
tracer flag, easy to trigger via an `--aggressive-thresholds` preset,
and demonstrable end-to-end through a real-API demo script that
persists transcript + trace + metrics + summary to a timestamped
artifact directory.

## Last completed initiative

**Runtime Activation Plan** — see
[`initiatives/_archive/2026-05-runtime-activation/`](./initiatives/_archive/2026-05-runtime-activation/).

| | |
|---|---|
| Period | 2026-05-21 |
| Milestones | M1 → M5 |
| Final commit | `de3ecad` |
| pytest | 392 → 497 (+105) |
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
