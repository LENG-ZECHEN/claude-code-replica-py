# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**`plan-surface`** — see [`initiatives/current/PLAN.md`](./initiatives/current/PLAN.md).

| | |
|---|---|
| Bootstrapped | 2026-06-08 |
| Baseline | `17e616d` (pytest 835 passing, mypy + ruff clean) |
| Milestones | M1 → M3 (3 total; status: M1 next, M2 + M3 pending) |
| Commit prefix | `plan-srf` |
| Planned exit | All three milestones commit with `[plan-srf/M{N}]` prefixes, exit gates verified, pytest green |
| Owner brief | [`PLAN.md`](./initiatives/current/PLAN.md) |
| Next step | Run `./automation/scripts/run_all_milestones.sh` (see `automation/RUNBOOK.md` Phase 2) |

**What this initiative ships:** Claude Code's two flagship "planning surface" mechanisms in the Python replica.

- **M1 — TodoWrite (V1)**: single-tool, in-memory todo list with strict double-AND turn-based reminder (`TODO_REMINDER_TURNS=10`) that injects a USER-role `<system-reminder>` attachment when ≥10 assistant turns pass without a TodoWrite call AND ≥10 turns since the last reminder. NOT the V2 6-tool Tasks suite (file persistence / lockfile / DAG / swarm out of scope).
- **M2 + M3 — Plan Mode**: `PermissionMode` enum + `Tool.read_only` flag + per-turn `ATTACHMENT_PLAN_MODE` teaching attachment + `ToolExecutor` soft-deny + `/plan` bidirectional toggle + `ExitPlanMode` with CLI approval. The API `tools` field stays **mode-invariant** across NORMAL ↔ PLAN so the prompt cache prefix is preserved (mirrors TS `tools.ts:271-327 getTools` which doesn't filter by mode either).

> SIZING WAIVED in PLAN.md provenance: M1 and M2 each touch 11 src files but ~5 are 1-3 line trivial diffs. Implementation LOC ~80-110/milestone, well below the obs-thresholds M1 thrash precedent.

## Last completed initiative

**ctx-mgmt-demo** — see
[`initiatives/_archive/2026-05-ctx-mgmt-demo/`](./initiatives/_archive/2026-05-ctx-mgmt-demo/).

| | |
|---|---|
| Period | 2026-05-25 – 2026-05-25 |
| Milestones | M1 → M3 |
| Final commit | `f937d8f` (final pre-wrap content commit; archived by the `[ctx-demo/wrap]` commit) |
| pytest | 816 → 820 (+4) |
| mypy + ruff | clean (`src tests` and repo-wide `ruff check .`) |
| English review | [`REVIEW.md`](./initiatives/_archive/2026-05-ctx-mgmt-demo/REVIEW.md) |
| Owner brief 中文 | [`OWNER_BRIEF.zh-CN.md`](./initiatives/_archive/2026-05-ctx-mgmt-demo/OWNER_BRIEF.zh-CN.md) |

**What shipped:** two additive CLI flags — `--microcompact-minutes` (both
REPLs) and `--max-turns` (openai REPL) — plus real-DashScope (`qwen3.6-plus`)
per-mechanism demo artifacts and three notebooks under `demo/` for
snip+externalize, full compact, and microcompact.

**Review-and-repair note:** the review session fixed a `_build_repl_loop`
wiring bug (`tool_result_store` reached `ContextBuilder` but not `AgentLoop`,
so `/stats externalized_bytes` was always 0) with a 1-line fix + regression
test (`8ef0a4f`), cleaned 10 repo-wide ruff errors in the M2 capture driver
and dropped its private-attribute workaround (`a6049ce`), and synced
README + CLAUDE.md (`f937d8f`). Two LOW findings deferred (stale CLAUDE.md
"once per loop instance" wording in a protected section; an incomplete M2
PROGRESS counter line) — see `REVIEW.md`.

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
