# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**session-memory-dream** — bootstrapped 2026-06-15.
See [`initiatives/current/`](./initiatives/current/).

| | |
|---|---|
| Slug | `session-memory-dream` |
| Status | active — bootstrapped, NOT yet executed |
| Bootstrapped | 2026-06-15 |
| Milestones | M1 → M7 (7) |
| Commit prefix | `sm-dream` |
| Baseline commit | `094cf90` |
| Baseline pytest | 912 passing (+1 xpassed); mypy + ruff clean |
| Brief | [`PLAN.md`](./initiatives/current/PLAN.md) · [`config.yaml`](./initiatives/current/config.yaml) |

**What it builds:** the two remaining context/memory mechanisms that
complete fidelity to Claude Code v2.1.88 — **(A) session-memory
compaction** (reuse an incrementally-maintained session summary so
auto-compaction skips the compaction-time LLM summarization call) and
**(B) auto-dream** (a gated, forked sub-agent that periodically
consolidates — merges/dedups/prunes/re-indexes — the cross-session
memory store). Both ride on one new generic `ForkedAgentRunner`.

**Milestone arc:** M1 generic runner → M2–M4 session-memory
(state + summarizer → loop wiring + persistence → observability +
dual-arm latency benchmark) → M5–M7 dream (lock + gate cascade →
consolidator engine → CLI + trigger + docs). A disclosed, reproducible
wall-clock benchmark replaces the never-existed "98.7%" claim, and the
memory subsystem gains its missing 4th layer (periodic consolidation,
the counterpart to per-turn `extract_memories`).

**Next step (owner-triggered):** `./automation/scripts/run_all_milestones.sh`
runs every milestone, then auto-invokes the review + wrap-up agent.

## Last completed initiative

**plan-surface** — see
[`initiatives/_archive/2026-06-plan-surface/`](./initiatives/_archive/2026-06-plan-surface/).

| | |
|---|---|
| Period | 2026-06-08 – 2026-06-08 |
| Milestones | M1 → M3 |
| Final commit | `1e242b5` (final pre-wrap content commit; archived by the `[plan-srf/wrap]` commit) |
| pytest | 835 → 904 (+69; includes +5 review-fix regression tests) |
| mypy + ruff | clean (`mypy src/` and repo-wide `ruff check .`) |
| English review | [`REVIEW.md`](./initiatives/_archive/2026-06-plan-surface/REVIEW.md) |
| Owner brief 中文 | [`OWNER_BRIEF.zh-CN.md`](./initiatives/_archive/2026-06-plan-surface/OWNER_BRIEF.zh-CN.md) |

**What shipped:** Claude Code's two flagship "planning surface"
mechanisms in the Python replica — TodoWrite V1 (single-tool,
in-memory todo list with strict double-AND turn-based reminder) and
Plan Mode (`PermissionMode` enum + `Tool.read_only` flag +
per-turn `ATTACHMENT_PLAN_MODE` teaching attachment + `ToolExecutor`
soft-deny + `/plan` bidirectional toggle + `ExitPlanMode` with CLI
approval). The API `tools` field stays mode-invariant across NORMAL ↔
PLAN so the prompt cache prefix is preserved.

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
