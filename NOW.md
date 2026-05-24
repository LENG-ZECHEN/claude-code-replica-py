# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**None.**

`initiatives/current/` is empty (`.gitkeep` only).

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
