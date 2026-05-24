# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**ctx-mgmt-demo** — see
[`initiatives/current/`](./initiatives/current/).

| | |
|---|---|
| Slug | `ctx-mgmt-demo` |
| Bootstrapped | 2026-05-25 |
| Milestones | M1 → M3 |
| Baseline commit | `9ba662b` |
| Baseline pytest | 816 passing |
| Plan | [`PLAN.md`](./initiatives/current/PLAN.md) |
| Per-milestone prompts | [`prompts/`](./initiatives/current/prompts/) |
| Current handoff | [`HANDOFF.md`](./initiatives/current/HANDOFF.md) |

**Milestone summary:**

- **M1** — `cli-flags-microcompact-minutes-and-max-turns`: two
  additive CLI flags (`--microcompact-minutes` on both CLIs;
  `--max-turns` on `simple-agent-openai` REPL). ≤ 3 src files, ≥ 3
  new tests. No new abstractions.
- **M2** — `capture-real-api-artifacts-for-3-scenarios`: real
  DashScope API captures for snip+externalize, full compact, and
  microcompact scenarios. Pure side-effect; no src/. Artifacts
  committed under `demo/_artifacts/`.
- **M3** — `write-3-notebooks-and-readme`: notebook-style markdown
  embedding the M2 artifacts. Pure docs.

**Next step:** run `./automation/scripts/run_all_milestones.sh`
from `python-replica/`.

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

**Post-initiative follow-up on `main`** (`212b6af` fix + `8d20b1b` docs, 2026-05-24): a direct-to-`main` change resolved the four "wired but inert" recall/extraction defects from the review — `recent_tools` now reaches the selector, `find_relevant_memories` returns a `RecallResult` (accurate `memory_select` trace), the `extraction_in_progress` gate now guards re-entrancy, and the unused `read_file_state` param was removed — plus three LOW findings (extractor manifest stub, `tags` persistence, byte-accurate `MEMORY.md` truncation). **`main` is now at `8d20b1b`; pytest 807 → 816, mypy + ruff clean.**

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
