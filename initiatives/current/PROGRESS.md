# session-memory-dream progress log

Cumulative milestone log for the `session-memory-dream` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[sm-dream/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

Each milestone agent APPENDS one block at exit ritual, formatted:

```
## M{N} — done YYYY-MM-DD

- **commit**: `(see git log)` `[sm-dream/M{N}] <subject>`
- **tests**: <before> → <after> (+N)
- **mypy**: clean | **ruff**: clean
- **files changed**: `<file1>`, `<file2>`, ...
- **exit gate**: `<gate text from §2>` → PASS (<one-line evidence>)
- **notes**: <optional, ≤1 line>
```

<!-- Milestone blocks begin below. The first real milestone (M1) appends
     its block here; do not place any entry above this line. -->

## M1 — done 2026-06-15

- **commit**: `(see git log)` `[sm-dream/M1] extract ForkedAgentRunner from ExtractMemoriesRunner`
- **tests**: 912 → 923 (+11)
- **mypy**: clean | **ruff**: clean
- **files changed**: `src/simple_coding_agent/forked_agent.py`, `src/simple_coding_agent/extract_memories.py`, `tests/test_forked_agent.py`
- **exit gate**: `test_forked_agent.py passes (≥ 6 cases) AND existing test_extract_memories*.py stay green` → PASS (35 passed in targeted run; 923 total, +11 from 912)
- **notes**: Narrowed bare `except Exception: pass` in _build_whitelist_tools to `UnknownToolError` only; context injection bug fixed (base_messages now sent as context_messages)

## M2 — done 2026-06-15

- **commit**: `(see git log)` `[sm-dream/M2] add SessionMemoryState + incremental fold + SessionMemorySummarizer`
- **tests**: 923 → 951 (+28)
- **mypy**: clean | **ruff**: clean
- **files changed**: `src/simple_coding_agent/session_memory_state.py`, `src/simple_coding_agent/compact.py`, `tests/test_session_memory_state.py`, `tests/test_session_memory_summarizer.py`
- **exit gate**: `tests/test_session_memory_state.py AND tests/test_session_memory_summarizer.py pass; SessionMemoryState holds 9-section summary; to_jsonable/from_jsonable round-trip with unknown-key forward-compat; update_session_memory returns NEW state (immutability); warm SessionMemorySummarizer returns prewarmed text with ZERO provider calls; cold state delegates to fallback; ContextCompactor(summarizer=SessionMemorySummarizer(prewarmed)) produces non-empty CompactSummary; pytest grows by ≥12` → PASS (28 passed in targeted run; 951 total, +28 from 923)
- **notes**: Lazy import of RuleBasedSummarizer inside update_session_memory() avoids circular import (compact.py imports SessionMemoryState at module level)

## M3 — done 2026-06-15

- **commit**: `(see git log)` `[sm-dream/M3] wire session-memory into loop + LLM updater + cross-process persistence`
- **tests**: 951 → 962 (+11)
- **mypy**: clean | **ruff**: clean
- **files changed**: `src/simple_coding_agent/session_memory_state.py`, `src/simple_coding_agent/extraction_hooks.py`, `src/simple_coding_agent/session_store.py`, `src/simple_coding_agent/loop.py`, `src/simple_coding_agent/cli.py`, `src/simple_coding_agent/openai_cli.py`, `tests/test_loop_session_memory.py`, `tests/test_end_to_end_long_session.py`, `tests/test_repl_save_load.py`
- **exit gate**: `maybe_update_session_memory runs in _run_stop_hooks; warm SM → _force_compact → ZERO provider calls (MockProvider delta=0); cross-process warm resume preserves SM; cold SM falls back without crash; pytest grows by ≥10` → PASS (14 passed in targeted run; 962 total, +11 from 951)
- **notes**: Synchronous stop-hook fold replaces TS fire-and-forget async extraction; load_session now returns 3-tuple (transcript, summary, SessionMemoryState)

## M4 — done 2026-06-15

- **commit**: `(see git log)` `[sm-dream/M4] SM-compact observability + dual-arm latency benchmark`
- **tests**: 962 → 969 (+7)
- **mypy**: clean | **ruff**: clean
- **files changed**: `src/simple_coding_agent/metrics.py`, `src/simple_coding_agent/loop.py`, `benchmarks/bench_sm_compact_latency.py`, `benchmarks/_results/04_sm_compact_latency.json`, `benchmarks/_results/04_sm_compact_latency.md`, `tests/test_bench_sm_compact.py`, `tests/test_metrics_collector.py`
- **exit gate**: `MetricsCollector gains sm_compact_reuses/misses; reused=<bool> on compact trace channel; bench_sm_compact_latency.py two-arm deterministic+real-API; test_bench_sm_compact.py asserts reuse_ms < full_ms; pytest grows by ≥7` → PASS (15 passed in targeted run; 969 total, +7 from 962; deterministic artifacts: full=0.399ms → reuse=0.291ms; StderrTracer emits reused=True/False on compact channel)
- **notes**: reused=True emitted as second compact trace emit from _force_compact (compact.py also emits compact trace inside compact()); multiple emits on same channel is allowed
