# ctx-mgmt-pdf-align progress log

Cumulative milestone log for the `ctx-mgmt-pdf-align` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[ctx-pdf/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

<!-- No milestone blocks yet. The first real milestone (M1) appends its
     own block at exit ritual step 3, using the shape:

## M{N} — done YYYY-MM-DD

- **commit**: `<sha>` `[ctx-pdf/M{N}] <subject>`
- **tests**: <prev> → <new> (+<delta>)
- **mypy**: <status> | **ruff**: <status>
- **files changed**: `<file1>`, `<file2>`, ...
- **exit gate**: `<gate text from §2 of the milestone prompt>` → PASS (<one-line evidence>)
- **notes**: <optional, ≤1 line. Anything longer goes in HANDOFF.md.>
-->

## M1 — done 2026-05-23

- **commit**: `[ctx-pdf/M1]` compact-thresholds-and-llm-default (SHA in git log)
- **tests**: 615 → 632 (+17; +14 in test_compact.py, +3 in test_repl.py)
- **mypy**: clean (21 files) | **ruff**: clean
- **files changed**: `src/simple_coding_agent/compact.py`, `src/simple_coding_agent/cli.py`, `tests/test_compact.py`, `tests/test_repl.py`, `tests/test_loop.py`, `tests/test_metrics_collector.py`, `tests/test_microcompact_runtime.py`, `examples/microcompact_demo.py`
- **exit gate**: microcompact keep_recent=5 default preserves 5 newest compactable results; should_compact True iff `used >= max_tokens - output_headroom(12k) - compact_headroom(20k)` AND `used >= min_session_tokens(30k)`, legacy ratio preserved as 2nd trigger; ContextCompactor(provider=...) defaults to LLMSummarizer, provider=None keeps RuleBasedSummarizer → PASS (8 named gate tests + 632 green)
- **notes**: keep_recent=5 default changed runtime; 4 pre-PDF clearing assertions (test_loop/test_metrics_collector/test_microcompact_runtime + microcompact_demo) now construct keep_recent=0 per the exit-gate parenthetical.

## M2 — done 2026-05-23

- **commit**: `[ctx-pdf/M2]` engine-snip-orphan-and-ancient-pairs (SHA in git log)
- **tests**: 632 → 647 (+15; all in test_snip.py)
- **mypy**: clean (21 files) | **ruff**: clean
- **files changed**: `src/simple_coding_agent/snip.py`, `src/simple_coding_agent/models.py`, `src/simple_coding_agent/context.py`, `tests/test_snip.py`
- **exit gate**: snip() deletes orphan tool_use AND orphan tool_result blocks; deletes paired cleared (tool_use,tool_result) oldest-first once summed cleared tokens >= `ancient_cleared_threshold_tokens` (default 10_000), evicting only until below threshold; inserts exactly one `SNIP_BOUNDARY` (new MessageType + Message.snip_boundary(), is_meta=True) at earliest deletion; SNIP_BOUNDARY filtered in `_normalize_messages` beside COMPACT_BOUNDARY → PASS (647 green, +15; 13 existing snip cases unmodified)
- **notes**: orphan delete applies to all tools (API-validity GC, not P8 folding); deletion never creates new orphans so re-snip is a no-op (no double boundary).
