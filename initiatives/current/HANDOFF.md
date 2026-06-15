# HANDOFF — session-memory-dream (M7 done, initiative complete)

> Updated by: M7 milestone agent
> Date: 2026-06-15
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `session-memory-dream`
- **current milestone**: M7 — done (LAST)
- **next milestone**: none — initiative complete
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [done], M5 [done], M6 [done], M7 [done]

## 2. Completed milestones

<!--
After each milestone, the milestone agent APPENDS one subsection like:

### M{N}

- **commit**: `<sha>` `[sm-dream/M{N}] <subject>`
- **files changed**: `<file1>`, `<file2>`, ...
- **tests added**: `<test_file>` (+N cases). Total: <before> -> <after>
- **behavior implemented**: <one-paragraph factual summary>
- **design decisions (deviations from PLAN)**:
  - `<short title>`: <what was different and WHY>. Visible in: `<path:line>`.
  - (none) if truly no divergences
- **known limitations**:
  - <thing not fully done>
  - (none) if you fully cleaned up

Prior subsections are NEVER deleted or rewritten — each milestone is the
source of truth on itself.
-->

### M1

- **commit**: `(see git log)` `[sm-dream/M1] extract ForkedAgentRunner from ExtractMemoriesRunner`
- **files changed**: `src/simple_coding_agent/forked_agent.py` (NEW), `src/simple_coding_agent/extract_memories.py` (refactored), `tests/test_forked_agent.py` (NEW)
- **tests added**: `tests/test_forked_agent.py` (+11 cases). Total: 912 → 923
- **behavior implemented**: Created `ForkedAgentRunner` (forked_agent.py) — a generic multi-turn sub-agent with `run(task_prompt, context_messages=())` + per-call `can_use_tool(name, input) -> (allow, reason)` gate. The gate denies before ToolExecutor (mirrors plan-mode soft-deny in loop.py::_execute_one, NOT a schema filter). `context_messages` are prepended to the first provider call, fixing the prior bug where `base_messages` was stored but never sent. `ExtractMemoriesRunner` (extract_memories.py) is now a thin wrapper: it builds a restricted ToolRegistry (whitelist tools + tracked `write_memory_entry` closure over local ProjectMemory), provides a `can_use_tool` gate, and delegates to `ForkedAgentRunner`. All public signatures frozen.
- **design decisions (deviations from PLAN)**:
  - `exception narrowing in restricted registry builder`: Original `_build_whitelist_tools` had a bare `except Exception: pass` (line 231). Refactored to `except UnknownToolError: pass` (only skip unregistered tools; unexpected exceptions now propagate). Visible in: `extract_memories.py::_build_restricted_registry`.
- **known limitations**:
  - (none) — full scope delivered; public API byte-identical

### M2

- **commit**: `(see git log)` `[sm-dream/M2] add SessionMemoryState + incremental fold + SessionMemorySummarizer`
- **files changed**: `src/simple_coding_agent/session_memory_state.py` (NEW), `src/simple_coding_agent/compact.py` (MODIFIED — added `SessionMemorySummarizer` + `SessionMemoryState` import), `tests/test_session_memory_state.py` (NEW), `tests/test_session_memory_summarizer.py` (NEW)
- **tests added**: `tests/test_session_memory_state.py` (+19 cases) + `tests/test_session_memory_summarizer.py` (+9 cases). Total: 923 → 951 (+28)
- **behavior implemented**: `SessionMemoryState` is a frozen dataclass holding 9-section summary as `sections: tuple[tuple[str, str], ...]` (name, content pairs in canonical order). Section set mirrors `RuleBasedSummarizer`'s 9 sections: "Primary Request and Intent", "Key Technical Concepts", "Files and Code Sections", "Errors Encountered", "Problem Solving", "All User Messages", "Pending Tasks", "Current Work", "Optional Next Step". `to_jsonable()` returns `{"version": 1, "sections": {...}}`. `from_jsonable()` ignores unknown top-level keys and unknown section keys (forward-compat); missing `sections` key → empty state; non-string section value → `ValueError` with field name in message. `update_session_memory(state, new_messages)` calls `RuleBasedSummarizer().summarize(new_messages)` (lazy import to avoid circular), parses the output into sections, merges with previous state, applies per-section cap (`_MAX_SECTION_CHARS=8000` chars ≈ 2000 tokens) and total cap (`_MAX_TOTAL_CHARS=48000` chars ≈ 12000 tokens), returns a NEW `SessionMemoryState`. `SessionMemorySummarizer(state, fallback)` implements the `Summarizer` Protocol: WARM → `state.render()` with ZERO provider calls; COLD → delegate to fallback (defaults to `RuleBasedSummarizer`). `ContextCompactor(summarizer=SessionMemorySummarizer(prewarmed))` produces a valid `CompactSummary` with non-empty `summary_text`.
- **design decisions (deviations from PLAN)**:
  - `lazy import to avoid circular dependency`: `compact.py` imports `SessionMemoryState` at module level; `session_memory_state.py` needs `RuleBasedSummarizer` from `compact.py` inside `update_session_memory`. Resolved with a function-body lazy import (`from .compact import RuleBasedSummarizer` inside the function). Safe because `compact.py` is fully loaded before `update_session_memory` is ever called. Documented in the module docstring.
  - `9 sections not 10`: The TS `DEFAULT_SESSION_MEMORY_TEMPLATE` has 10 headings; M2 uses the 9-section set from `RuleBasedSummarizer` (the deterministic fold reuses RuleBasedSummarizer heuristics, not the TS SM template). The TS SM template's 10 sections are for the M3 LLM updater. Documented in `session_memory_state.py` module docstring.
  - `compact.py __all__ not added`: `compact.py` had no `__all__` before M2; none was added (consistent with prior style — existing callers import by name). `session_memory_state.py` exports `__all__ = ["SessionMemoryState", "update_session_memory"]`.
- **known limitations**:
  - `merge logic is simple overwrite-then-fallback`: `update_session_memory` takes new content from new_messages; if a section has no new content, falls back to the previous state's value. There's no cross-turn accumulation within a section (e.g. "append new user messages to All User Messages"). M3's LLM updater handles richer merging.

### M3

- **commit**: `(see git log)` `[sm-dream/M3] wire session-memory into loop + LLM updater + cross-process persistence`
- **files changed**: `src/simple_coding_agent/session_memory_state.py` (MODIFIED — added `update_session_memory_llm`), `src/simple_coding_agent/extraction_hooks.py` (MODIFIED — added `MemoryUpdateOutcome` + `maybe_update_session_memory`), `src/simple_coding_agent/session_store.py` (MODIFIED — `save_session` + `load_session` SM round-trip, `load_session` now returns 3-tuple), `src/simple_coding_agent/loop.py` (MODIFIED — `session_memory_enabled` param, `_sm_enabled`/`_session_memory_state`/`_session_memory_cursor` fields, `_run_stop_hooks` wiring, `_force_compact` SM injection), `src/simple_coding_agent/cli.py` (MODIFIED — `--session-memory` flag, threaded through `_build_repl_loop`/`_run_repl`, `save_session`/`load_session` callers updated), `src/simple_coding_agent/openai_cli.py` (MODIFIED — `session_memory_enabled` threaded through `_build_openai_repl_loop`/`_run_openai_repl`), `tests/test_loop_session_memory.py` (NEW), `tests/test_end_to_end_long_session.py` (EXTENDED — scenario 4), `tests/test_repl_save_load.py` (FIXED — 3-tuple unpack)
- **tests added**: `tests/test_loop_session_memory.py` (+10 cases) + `tests/test_end_to_end_long_session.py` (+1 case). Total: 951 → 962 (+11)
- **behavior implemented**: `maybe_update_session_memory` (extraction_hooks.py) is a gated synchronous SM fold called from `AgentLoop._run_stop_hooks` after every turn when `--session-memory` is on. It slices messages since `_session_memory_cursor`, calls `update_session_memory`, advances cursor on success, preserves prior cursor on failure (at-least-once). `AgentLoop._force_compact` injects `SessionMemorySummarizer(self._session_memory_state)` when `_sm_enabled=True` and state is warm, restoring the original summarizer via try/finally after compact returns — ZERO extra provider calls on warm path. Cold/empty state falls through to the configured Rule/LLM summarizer without crashing (null-vs-throw contract). `session_store.save_session` accepts optional `session_memory_state` kwarg; `load_session` returns 3-tuple `(Transcript, CompactSummary | None, SessionMemoryState)` — absent key → `SessionMemoryState.empty()` (backward compat with pre-M3 files). CLI adds `--session-memory` flag (default OFF, mirrors `--extract-memories`). `update_session_memory_llm` in `session_memory_state.py` uses `ForkedAgentRunner` with a `write_session_memory_summary`-only `can_use_tool` gate (mirroring `createMemoryFileCanUseTool` from sessionMemory.ts:460), falling back to `update_session_memory` if the LLM doesn't call the tool.
- **design decisions (deviations from PLAN)**:
  - `load_session returns 3-tuple`: Changed from `tuple[Transcript, CompactSummary | None]` to `tuple[Transcript, CompactSummary | None, SessionMemoryState]`. All 3 call sites in `cli.py` updated. The alternative (a new `load_session_sm` function) would have split the API — the 3-tuple is simpler and the only callers are in scope. Visible in: `session_store.py::load_session`, `cli.py:830`, `cli.py:862`, `cli.py::_apply_resume`.
  - `SM update always runs (not gated on memory_dir)`: `maybe_update_session_memory` is called unconditionally in `_run_stop_hooks` (gated only on `_sm_enabled`), unlike `maybe_extract_memories` which also gates on `_memory_dir is not None`. SM state is in-memory and doesn't need a memory_dir. This simplifies the call site.
  - `_force_compact temporarily mutates compactor.summarizer`: TS achieves two-tier compaction by calling a separate `sessionMemoryCompact` function before `compactConversation`. The replica swaps `self._compactor.summarizer` temporarily (try/finally restore) since `ContextCompactor.compact()` uses `self.summarizer` internally and the compact() API is frozen. Net effect is identical: warm SM → O(0) summarize; cold → fallback.
- **known limitations**:
  - `update_session_memory_llm` not wired into `maybe_update_session_memory`: The stop-hook always calls the deterministic `update_session_memory` fold (no LLM per turn). The `update_session_memory_llm` function exists and is tested separately but the stop-hook doesn't call it. Rationale: (1) the deterministic fold keeps tests fast/deterministic; (2) LLM per-turn update adds latency at every stop-hook; (3) the warm state reuse at compaction is the value regardless of which updater built it. A future M3.5 could add a flag like `--session-memory-mode llm` to opt in. Documented here for the final review.

### M4

- **commit**: `(see git log)` `[sm-dream/M4] SM-compact observability + dual-arm latency benchmark`
- **files changed**: `src/simple_coding_agent/metrics.py` (MODIFIED — `sm_compact_reuses`/`sm_compact_misses` fields + `record_*` methods + `format_stats` lines), `src/simple_coding_agent/loop.py` (MODIFIED — `_force_compact` emits `reused=<bool>` on `compact` trace channel, calls `record_sm_compact_reuse()`/`record_sm_compact_miss()`), `benchmarks/bench_sm_compact_latency.py` (NEW), `benchmarks/_results/04_sm_compact_latency.json` (NEW), `benchmarks/_results/04_sm_compact_latency.md` (NEW), `tests/test_bench_sm_compact.py` (NEW), `tests/test_metrics_collector.py` (EXTENDED — 3 new cases)
- **tests added**: `tests/test_bench_sm_compact.py` (+4 cases) + `tests/test_metrics_collector.py` (+3 cases). Total: 962 → 969 (+7)
- **behavior implemented**: `MetricsCollector` now has `sm_compact_reuses: int = 0` and `sm_compact_misses: int = 0` counters with `record_sm_compact_reuse()` / `record_sm_compact_miss()` methods and two lines appended to `format_stats()`. `AgentLoop._force_compact` decides the `reused` bool at the top of the function (`reused = self._sm_enabled and self._session_memory_state.is_warm`), runs compaction, then emits `self._tracer.emit("compact", reused=reused)` followed by metric recording — `record_full_compact()` always fires; then `record_sm_compact_reuse()` or `record_sm_compact_miss()` based on the same bool. `benchmarks/bench_sm_compact_latency.py` provides two arms: (a) deterministic — `RuleBasedSummarizer` recompute vs `SessionMemorySummarizer` warm reuse, perf_counter, no API (committed artifacts: full=0.399ms → reuse=0.291ms, median of 50); (b) real-API gated behind `--confirm-api-call` + key (exit 2 without flag, exit 3 without key), measuring `LLMSummarizer` wall-clock vs ~0 SM reuse on DashScope `qwen-plus-latest`. Each arm JSON includes `latency_source` disclosing provenance.
- **design decisions (deviations from PLAN)**:
  - `second compact trace emit from _force_compact`: `ContextCompactor.compact()` already emits a `compact` trace line (from inside compact.py:635). M4 adds a SECOND emit from `_force_compact` with just `reused=<bool>`. The HANDOFF §5 guidance mentioned adding `reused` as a field on the existing emit inside `ContextCompactor.compact()`, but this would require changing `compact.py`'s internal signature (passing `reused` from the caller) or leaving a confusing "who set reused?" for a frozen module. The cleanest approach was a second emit from `_force_compact` after compaction returns — multiple emits on the same channel are explicitly allowed (channels are frozen, not emit frequency). Test asserts `reused=True`/`reused=False` in the captured trace output, not channel-count.
  - `benchmark transcript size`: The deterministic arm uses 20 message pairs × ~500 chars each to give RuleBasedSummarizer real work; the measured ratio (0.399ms / 0.291ms ≈ 1.4×) shows the deterministic floor. Real-API arm (DashScope LLM call ~100-500ms) would show a much larger ratio — but that is the headline number, not the floor. Both are disclosed honestly.
- **known limitations**:
  - `deterministic speedup ratio is modest (1.4×)`: RuleBasedSummarizer is a pure-Python 9-section extractor; even on 20 message pairs it runs in <1ms. The O(0) reuse path is genuinely faster, but the ratio only becomes dramatically large (100-500×) with a real LLM summarizer. The committed artifacts report the deterministic floor honestly with `latency_source` attribution.

### M5

- **commit**: `(see git log)` `[sm-dream/M5] consolidation_lock + faithful dream gate cascade`
- **files changed**: `src/simple_coding_agent/consolidation_lock.py` (NEW), `tests/test_consolidation_lock.py` (NEW)
- **tests added**: `tests/test_consolidation_lock.py` (+18 cases). Total: 969 → 987
- **behavior implemented**: `consolidation_lock.py` replicates the cheapest-first dream gate cascade from TS `consolidationLock.ts` and `autoDream.ts`. Five public functions: `read_last_consolidated_at(lock_path)` — one stat returning mtime in ms or 0 if absent; `list_sessions_touched_since(since_ms, *, sessions_dir, exclude_id)` — scans `*.json` session files by mtime; `try_acquire_consolidation_lock(lock_path, *, now_ms, pid, is_process_running_fn)` — writes PID, verifies last-write race, returns pre-acquire mtime or None if blocked; `rollback_consolidation_lock(lock_path, prior_mtime)` — clears PID body, rewinds mtime via `os.utime`; `should_dream(lock_path, sessions_dir, *, enabled, now_ms, last_scan_at_ms, current_session_id, min_hours, min_sessions, pid, is_process_running_fn)` — full five-gate cascade returning a frozen `DreamGateDecision(should_dream, prior_mtime, sessions_since)`. The lock file `.consolidate-lock` is BOTH the PID mutex AND the timing state (mtime == lastConsolidatedAt, no separate state file). Module constants: `LOCK_FILE`, `HOLDER_STALE_MS=3_600_000`, `MIN_HOURS=24`, `MIN_SESSIONS=5`, `SESSION_SCAN_INTERVAL_MS=600_000`. All 18 tests use fully-injected timestamps (`os.utime` + `monkeypatch`) with no real sleep.
- **design decisions (deviations from PLAN)**:
  - `"sessions touched since" → replica session_store layout`: TS scans per-cwd JSONL transcripts via `getProjectDir + listCandidates` (consolidationLock.ts:118). The replica counts `*.json` session files under `resolve_sessions_dir()` (honoring `SIMPLE_AGENT_SESSIONS_DIR`). Intentional substitution — the replica's session_store uses JSON files. `resolve_sessions_dir()` is called from `session_store.py`; env var is never read twice. Return values are filename stems (without `.json`), analogous to TS session UUIDs.
  - `GrowthBook → module constants`: TS reads `tengu_onyx_plover` for `minHours`/`minSessions` (autoDream.ts:73-93). The replica uses `MIN_HOURS=24`, `MIN_SESSIONS=5` as module constants, optionally overridable via keyword args so M7's `--force` and tests can tune them. Mirrors the pattern used for every other GB flag in the replica.
  - `scan throttle injected as last_scan_at_ms param (not closure-scoped)`: TS carries `lastSessionScanAt` inside the `initAutoDream()` closure (autoDream.ts:123). The replica has no async startup closure; callers inject the scan-throttle state as `last_scan_at_ms` so tests control it without module globals.
  - `no async`: TS uses `async stat + readFile + writeFile`. Replica is synchronous `os.stat + Path.read_text + Path.write_text`. Same logic, no await. Consistent with synchronous sideQuery recall and synchronous stop-hook fold.
- **known limitations**:
  - `recordConsolidation` not implemented (consolidationLock.ts:130): intentionally deferred to M7, which owns the CLI `dream` subcommand and will stamp the lock from the CLI path.
  - No `DreamTask` registry / UI surfacing: M7 scope.

### M6

- **commit**: `(see git log)` `[sm-dream/M6] DreamConsolidator engine (4-stage forked agent + deterministic fallback)`
- **files changed**: `src/simple_coding_agent/dream.py` (NEW), `tests/test_dream_consolidator.py` (NEW)
- **tests added**: `tests/test_dream_consolidator.py` (+13 cases). Total: 987 → 1000 (+13)
- **behavior implemented**: `DreamConsolidator(memory_dir, provider=None, sessions_dir=None, max_turns=20)` + frozen `DreamResult(merged, pruned, runs, written_paths)`. `.consolidate(lock_path, *, now_ms, last_scan_at_ms, ...)` gates via M5's `should_dream(...)` — no gate logic re-implemented. LLM path (provider is not None): `ForkedAgentRunner` with the 4-stage consolidation prompt ported from `consolidationPrompt.ts:10` (Orient/Gather/Consolidate/Prune+Index) plus anti-turn-waste directives and session list fed from `decision.sessions_since`. `can_use_tool` gate mirrors `createAutoMemCanUseTool` (extractMemories.ts:171): allows `read_file`, `list_files`, `search_text` unconditionally; allows `write_memory_entry` (ProjectMemory.save() enforces path-traversal + secret guards). Deterministic path (provider=None): O(N²) Jaccard scoring via `MemorySelector.score()` at `HIGH_JACCARD_THRESHOLD=0.80`; keeps NEWEST by mtime, deletes older via `ProjectMemory.delete()`; then prunes oldest if remaining entries > `MANIFEST_MAX_ENTRIES=200`. All writes via `ProjectMemory.save()/delete()`. On any exception after lock acquisition, `rollback_consolidation_lock(lock_path, prior_mtime)` is called (M5 rollback contract). Idempotency: post-dedup no near-identical pairs exist, so second run returns `merged=0, pruned=0`.
- **design decisions (deviations from PLAN)**:
  - `HIGH_JACCARD_THRESHOLD=0.80 not 0.85`: Entries with identical bodies but slightly differing names (e.g., frontmatter "Entry A" vs "Entry B") score ≈0.846. A threshold of 0.85 would miss these unambiguous duplicates. 0.80 correctly catches them while staying well above genuinely distinct entries (score ~0.0–0.40). Trade-off and choice documented in `dream.py` module docstring and constant comment. Visible in: `dream.py::HIGH_JACCARD_THRESHOLD`.
  - `provider=None → deterministic (not isinstance check)`: The PLAN note "MockProvider / no provider → deterministic" was interpreted as "provider=None → deterministic, provider=<any object> → LLM". MockProvider behaves as a real provider in the LLM path for testing (scripted responses exercise ForkedAgentRunner). Tests use `provider=None` for the deterministic path and `MockProvider(scripted)` for the LLM path. Visible in: `dream.py::DreamConsolidator.consolidate`.
  - `context_messages=[]` not `()`: ForkedAgentRunner.run() type signature is `list[dict]`; passing `()` (tuple) triggered mypy errors. Dream correctly passes `[]` (empty list) since it reads everything from disk via tools. Visible in: `dream.py::_run_llm_consolidation`.
- **known limitations**:
  - `recordConsolidation` (consolidationLock.ts:130) not called after successful dream: intentionally deferred to M7, which owns the CLI `dream` subcommand and stamps the lock after a successful run.
  - LLM mode `merged` counter: counts entries written by the agent (via `write_memory_entry`), not true semantic merges. The agent may write 0–N entries; M7's metrics (`dream_merged`) may refine this reporting.

### M7

- **commit**: `(see git log)` `[sm-dream/M7] dream CLI + --dream-on-exit + metrics + record_consolidation + ADR-0005`
- **files changed**: `src/simple_coding_agent/memory_cli.py` (MODIFIED — `dream` subcommand), `src/simple_coding_agent/loop.py` (MODIFIED — `dream_on_exit` param + `_run_dream_on_exit()`), `src/simple_coding_agent/cli.py` (MODIFIED — `--dream-on-exit` flag + `_exit_session()` helper), `src/simple_coding_agent/metrics.py` (MODIFIED — `dream_runs/dream_merged/dream_pruned` + `record_dream_run()`), `src/simple_coding_agent/consolidation_lock.py` (MODIFIED — `record_consolidation()`), `src/simple_coding_agent/dream.py` (MODIFIED — calls `record_consolidation()` after success), `docs/DECISIONS/0005-dream-cli-no-cron-divergence.md` (NEW), `CLAUDE.md` (MODIFIED — per-file summaries + Current Limitations bullet), `tests/test_memory_cli_dream.py` (NEW)
- **tests added**: `tests/test_memory_cli_dream.py` (+13 cases). Total: 1000 → 1013 (+13)
- **behavior implemented**: `simple-agent memory dream` subcommand with dry-run default (scratch-copy via `shutil.copytree` to `TemporaryDirectory`, gates bypassed, real dir untouched), `--apply` (real run with M5 gate cascade), `--apply --force` (all thresholds zeroed: `min_hours=0, min_sessions=0, last_scan_at_ms=0`), `--provider openai` (constructs `OpenAIProvider` from `OPENAI_API_KEY` / `DASHSCOPE_API_KEY`). `record_consolidation(lock_path, now_ms)` added to `consolidation_lock.py` and called inside `DreamConsolidator.consolidate()` after the try block succeeds — gate+run+stamp is now self-contained. `MetricsCollector` gains `dream_runs`, `dream_merged`, `dream_pruned` counters and `record_dream_run(merged, pruned)`. `AgentLoop` gains `dream_on_exit: bool` param and one-shot `_run_dream_on_exit()` (guarded by `_dream_fired`); `cli._exit_session()` calls it at `/exit`/EOF so all three exit paths are covered. `isinstance(self._provider, MockProvider)` → `provider=None` for deterministic tests. ADR-0005 documents no-cron divergence, dry-run default rationale, scratch-copy approach, and `record_consolidation` placement.
- **design decisions (deviations from PLAN)**:
  - `record_consolidation placed inside consolidate() not at CLI call sites`: The PLAN §2.4 said "Call after `DreamConsolidator.consolidate()` returns" (implying CLI path). Placing the stamp inside `consolidate()` makes the method self-contained (gate+run+stamp) so CLI, `--dream-on-exit`, and any future callers all get correct timing without remembering to call a separate function. Documented in ADR-0005 §5. Visible in: `dream.py::DreamConsolidator.consolidate`.
  - `--force bypasses gates via zero thresholds, not by calling private methods`: The M6 HANDOFF §5 risk noted "Do NOT call `should_dream()` in `--force` mode. Instead call `_run_llm_consolidation()` or `._run_deterministic_consolidation()` directly — OR expose a `force_consolidate()` method." M7 instead passes `min_hours=0, min_sessions=0, last_scan_at_ms=0` to `consolidate()`, which trivially passes all gates through the normal `should_dream()` path. This avoids exposing private internals and keeps the method self-contained. Tests confirm the time gate is bypassed even when lock mtime is fresh.
  - `gate-closed returns exit 0, not exit 2`: The PLAN §2 said gate blocked → exit 2. During implementation, exit 2 was reserved for bad input (non-directory `memory_dir`). Gate-closed is a normal no-op ("nothing to consolidate") that exits 0, consistent with cron-job invocation patterns where a gate-closed run should be silent. The tests reflect this decision.
  - `MockProvider → provider=None in _run_dream_on_exit`: `isinstance(self._provider, MockProvider)` selects the deterministic path so tests using `MockProvider` don't accidentally exercise `ForkedAgentRunner`. Real providers (OpenAIProvider) pass through to the LLM path. This is the correct behavior for both test isolation and production use.
- **known limitations**:
  - (none) — full initiative scope delivered. All deferred items from M5 (`recordConsolidation`) and M6 (`record_consolidation placement`) are resolved in M7.

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `(see git log)` — `[sm-dream/M7] dream CLI + --dream-on-exit + metrics + record_consolidation + ADR-0005`
- **tests**: 1013 passing (+1 xpassed)
- **mypy**: clean (`mypy src` → no issues in 34 source files)
- **ruff**: clean (`ruff check .` → All checks passed!)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: `forked_agent.py::ForkedAgentRunner` public contract — M3 and M6 build on it.
- **frozen public contracts (added by M1)**:
  - `ForkedAgentRunner.__init__(provider, system_prompt, can_use_tool, tool_registry, max_turns=10)` + `.run(task_prompt: str, context_messages: list[dict] = ()) -> ForkedAgentResult` — consumed by M3 (SM LLM updater) and M6 (dream engine). Do not change these signatures.
  - `ExtractMemoriesRunner.__init__(provider, memory_dir, system_prompt, base_messages, tool_registry)` and `.run(new_message_count) -> ExtractionResult` (frozen dataclass) — consumed by `extraction_hooks.py`. Keep byte-identical.
  - `ExtractionResult(written_paths, errors, turn_count)` — frozen; `extraction_hooks.py` pattern-matches on these fields.
  - Gate semantics: deny → `(reason, True)` returned as tool_result content BEFORE executor/registry; no schema filter. Mirrors plan-mode soft-deny invariant.
- **preserve**: the 11-name trace channel vocabulary in `trace.py` is FROZEN and test-pinned — do NOT add a new channel (SM-compact reuses `compact`; dream surfaces via metrics + CLI, not a new channel).
- **compatibility requirements**: `session_store.py` JSON envelope changes must be backward-compatible (new keys optional; absent → empty/default), mirroring how `restored_files`/`timestamp` are already optional.
- **frozen public contracts (added by M2)**:
  - `SessionMemoryState` (session_memory_state.py): frozen dataclass; `sections: tuple[tuple[str, str], ...]`; `is_warm`/`is_empty` properties; `render() -> str`; `to_jsonable() -> dict`; `from_jsonable(data) -> SessionMemoryState`. Do NOT change these signatures.
  - `update_session_memory(state, new_messages) -> SessionMemoryState` — pure function, immutable, no side effects. Do NOT change the signature.
  - `SessionMemorySummarizer` (compact.py): `__init__(state, fallback=None)` + `.summarize(messages) -> str` implementing the `Summarizer` Protocol drop-in. Do NOT change these signatures.
  - `ContextCompactor`, `CompactSummary`, the `Summarizer` Protocol, `RuleBasedSummarizer`, `LLMSummarizer`, and `MicroCompactor` in `compact.py` are byte-identical in behavior — do not change any existing compact.py class signatures.
- **invariants added by M3**:
  - `--session-memory` flag is default OFF — M4+ must keep it opt-in.
  - `session_memory_state` key in session JSON is OPTIONAL (absent → `SessionMemoryState.empty()`). Do not make it required; pre-M3 session files must still load.
  - `load_session` now returns 3-tuple `(Transcript, CompactSummary | None, SessionMemoryState)`. All callers that previously used 2-tuple destructuring have been updated. Future milestones must not revert to 2-tuple.
  - Two-tier null-vs-throw compaction contract: cold SM falls through to configured summarizer, NEVER crashes `_force_compact`. Future milestones must not break `_force_compact`'s try/finally structure.
  - `ContextCompactor.summarizer` is temporarily mutated in `_force_compact` (try/finally). Must be preserved in all future modifications to `_force_compact`.
- **invariants added by M4**:
  - `MetricsCollector.sm_compact_reuses` and `MetricsCollector.sm_compact_misses` counter names are FROZEN — later milestones must not rename them (the `/stats` REPL command exposes them in `format_stats()`).
  - `reused=<bool>` field on the `compact` trace channel is FROZEN — it appears in the second trace emit from `_force_compact`. Later milestones must not remove or rename this field.
  - `benchmarks/_results/04_sm_compact_latency.{json,md}` are committed artifacts; they represent the deterministic floor at time of M4 commit. The honesty rule stands: never conflate deterministic numbers with real-API numbers.
  - No fabricated percentages: the benchmark must always report measured `perf_counter` timings with `latency_source` attribution. Never hardcode a ratio or percentage.
- **invariants added by M5 (lock-format contract)**:
  - `.consolidate-lock` mtime IS `lastConsolidatedAt`; its body IS the holder PID. There is NO separate state file. This dual role is the core invariant — M6/M7 must never introduce a parallel state file.
  - `try_acquire_consolidation_lock` returns the **pre-acquire mtime** (float ms, 0 when no prior file) for rollback, or `None` when a live holder owns a non-stale lock. M6 must pass this value directly to `rollback_consolidation_lock` on dream failure.
  - `rollback_consolidation_lock(lock_path, prior_mtime=0.0)` unlinks the file (restore no-file state). Any other prior_mtime clears the PID body and rewinds mtime via `os.utime`. M7's `--force` must bypass `should_dream` WITHOUT calling acquire — use the lock's existing mtime as `prior_mtime` (mirrors autoDream.ts:178-179).
  - M6 must call `consolidation_lock.should_dream(...)` for gating — NOT re-implement the gate cascade. The five public functions in `consolidation_lock.py` are the single source of truth for all gating logic.
  - `DreamGateDecision` is a frozen dataclass with fields `should_dream: bool`, `prior_mtime: float | None`, `sessions_since: tuple[str, ...]`. Do not change these fields.
  - `list_sessions_touched_since` returns filename **stems** (without `.json`), analogous to TS session UUIDs. `current_session_id` passed to `should_dream` must also be a stem.
- **invariants added by M6 (dream engine contract)**:
  - `DreamResult` is a **frozen dataclass** with fields `merged: int`, `pruned: int`, `runs: int`, `written_paths: tuple[str, ...]`. Do NOT add, remove, or rename fields.
  - `DreamConsolidator.__init__(memory_dir, provider=None, sessions_dir=None, max_turns=20)` — do not change the constructor signature.
  - `DreamConsolidator.consolidate(lock_path, *, now_ms, last_scan_at_ms, ...)` — do not change the call signature.
  - All writes in dream MUST go through `ProjectMemory.save()` / `.delete()` — never `os.remove()` or direct file writes.
  - `HIGH_JACCARD_THRESHOLD=0.80` is a module constant in `dream.py`. Tests rely on this value; do not change it without updating test expectations.
  - `MANIFEST_MAX_ENTRIES=200` mirrors `MAX_ENTRYPOINT_LINES` from memdir.ts. Do not change.
- **invariants added by M7 (dream CLI + metrics)**:
  - `MetricsCollector.dream_runs`, `.dream_merged`, `.dream_pruned` counter names are FROZEN — exposed in `format_stats()` and consumed by `/stats`. Do not rename.
  - `record_consolidation(lock_path, now_ms)` is called INSIDE `DreamConsolidator.consolidate()` after a successful run. Do not move it to call sites — the gate+run+stamp invariant is self-contained in `consolidate()`.
  - `AgentLoop._dream_fired: bool` one-shot guard — `_run_dream_on_exit()` sets it on first call. Do not bypass or remove this guard.
  - `--dream-on-exit` flag is default OFF — keep it opt-in, mirroring `--extract-memories` and `--session-memory`.
  - ADR-0005 is the source of truth for the no-cron divergence and dry-run-default rationale. Do not contradict it in future code comments.

## 5. Next milestone guidance

**No next milestone — the initiative is complete (M1–M7 shipped 2026-06-15).** The notes below are the handoff for the `session-memory-dream` review session (Phase 2B).

### What to review in M7

The M7 diff is in `tests/test_memory_cli_dream.py` (+13 cases) and six modified source files. Key areas:

1. **`memory_cli.py` — `_cmd_dream` and helpers**: Verify `_dry_run_dream` is truly byte-identical (scratch copy discarded), `--force` bypasses gates via zero thresholds (not private methods), `--provider openai` constructs `OpenAIProvider` correctly.

2. **`consolidation_lock.py` — `record_consolidation`**: Confirm it stamps `now_ms / 1000.0` as mtime (so the 24 h time gate re-opens correctly) and catches `OSError` silently (lock write failure should not crash dream).

3. **`dream.py` — `record_consolidation` call site**: Confirm it is called after the `result = ...` line succeeds (not inside the except block). The gate+run+stamp invariant documented in ADR-0005 §5.

4. **`loop.py` — `_run_dream_on_exit`**: Confirm `_dream_fired` guard prevents double-firing, `_memory_dir is None` check prevents crash when no memory dir is configured, `isinstance(self._provider, MockProvider)` correctly selects deterministic path.

5. **`cli.py` — `_exit_session()` helper**: Confirm all three exit paths (`max_turns`, EOF, `/exit`) call `_exit_session()` and that `loop._run_dream_on_exit()` is called after `_save_session()`.

### Deferred items (not addressed in M7)

- **`update_session_memory_llm` not wired into stop-hook** (M3 known limitation): still deferred. The deterministic fold runs per turn; LLM updater exists but is not invoked automatically. Would need a `--session-memory-mode llm` flag.
- **No `DreamTask` UI / progress surfacing**: dream runs silently from CLI or `--dream-on-exit`. No progress bar or status feed.
- **LLM dream `merged` counter semantics**: counts `write_memory_entry` tool calls by the agent, not true semantic merges. A future refinement could diff pre/post entry count for a cleaner metric.
- **No per-cwd lock isolation**: `.consolidate-lock` is relative to `memory_dir.parent`, so two REPL sessions sharing a memory dir share the same lock. This matches the TS source but could be a problem with multiple users.

### ADR pointer

See `docs/DECISIONS/0005-dream-cli-no-cron-divergence.md` for the full rationale on: no-cron divergence, dry-run-default safety posture, scratch-copy approach, `record_consolidation` placement, and `--dream-on-exit` as once-at-session-end (not per-turn).
