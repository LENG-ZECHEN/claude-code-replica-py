# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**None.**

`initiatives/current/` is empty (`.gitkeep` only).

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

**Review-and-repair note:** the review session fixed one HIGH
(`plan_mode_exits_rejected` was structurally added in M3 but
operationally dead — the rejection branch raised `PlanRejectedError`
before any counter bump; fix wires a `metrics=` kwarg through
`register_exit_plan_mode_tool` and bumps in the rejection branch),
two MEDIUM (soft-deny `ToolResult` content lost the PLAN-spec
"Use exit_plan_mode / use /plan" recovery hint; `simple-agent-openai`
silently ignored the `--no-todo-reminder` / `--todo-reminder-turns`
flags PLAN required on both REPLs), and one LOW
(`transcript.normalize_for_api` filter list drifted from
`compact.py`). Review-fix commit `4efc445` ships 5 new tests across
`test_exit_plan_mode.py` and `test_openai_cli_repl.py`. Doc work
landed in `1e242b5`: four CLAUDE.md per-file summary appends, a
README.md flag-paragraph append, two subsystem docs (`docs/todo.md`,
`docs/plan-mode.md`), and ADR-0004 for the three-layer registration
pattern. Five LOW findings deferred — see `REVIEW.md`'s deferred
ledger.

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
