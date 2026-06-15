# NOW — current initiative status

> One-page pointer to what is actively happening in this repo.
> Rewritten by `automation/RUNBOOK.md` Phase 1 (bootstrap) and Phase 2
> (review + wrap-up). Anything else should not modify it.

## Active initiative

**None.**

`initiatives/current/` is empty (`.gitkeep` only).

## Last completed initiative

**session-memory-dream** — see
[`initiatives/_archive/2026-06-session-memory-dream/`](./initiatives/_archive/2026-06-session-memory-dream/).

| | |
|---|---|
| Period | 2026-06-15 – 2026-06-15 |
| Milestones | M1 → M7 |
| Final commit | `0d721ac` (final pre-wrap content commit; archived by the `[sm-dream/wrap]` commit) |
| pytest | 912 → 1016 (+104; includes +3 review-fix regression tests) |
| mypy + ruff | clean (`mypy src/` 34 source files, `ruff check .` all checks passed) |
| English review | [`REVIEW.md`](./initiatives/_archive/2026-06-session-memory-dream/REVIEW.md) |
| Owner brief 中文 | [`OWNER_BRIEF.zh-CN.md`](./initiatives/_archive/2026-06-session-memory-dream/OWNER_BRIEF.zh-CN.md) |

**What shipped:** the two missing context/memory mechanisms that complete
fidelity to Claude Code v2.1.88 — **(A) session-memory compaction**
(reuse an incrementally-maintained 9-section summary so `_force_compact`
adds zero summarization provider calls on warm reuse) and **(B) auto-dream**
(a 5-gate-cascade-gated, forked sub-agent that consolidates the
cross-session memory store via a ported 4-stage prompt or a deterministic
Jaccard / mtime fallback). Both build on a new generic
`ForkedAgentRunner` (`forked_agent.py`) extracted from
`ExtractMemoriesRunner` with per-call `can_use_tool` gating and a
real-bug fix for prior `base_messages` non-injection. A dual-arm
benchmark (`benchmarks/bench_sm_compact_latency.py`) replaces a
previously-unbacked "98.7%" claim with disclosed `perf_counter` numbers
(deterministic floor + DashScope real-API arm).

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
