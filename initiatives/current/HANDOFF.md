# HANDOFF — session-memory-dream (M5 done, next: M6)

> Updated by: M5 milestone agent
> Date: 2026-06-15
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `session-memory-dream`
- **current milestone**: M5 — done
- **next milestone**: `M6` — DreamConsolidator engine (4-stage forked agent + deterministic fallback)
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [done], M5 [done], M6 [next], M7 [pending]

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

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `(see git log)` — `[sm-dream/M5] consolidation_lock + faithful dream gate cascade`
- **tests**: 987 passing (+1 xpassed)
- **mypy**: clean (`mypy src` → no issues in 33 source files)
- **ruff**: clean (`ruff check .` → All checks passed!)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

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

## 5. Next milestone guidance

For `M6` — DreamConsolidator engine (4-stage forked agent + deterministic fallback):

- **next scope** (from PLAN.md M6):
  1. New `src/simple_coding_agent/dream.py::DreamConsolidator`. LLM mode runs `ForkedAgentRunner` (M1) with the ported 4-stage consolidation prompt (Orient / Gather / Consolidate / Prune+Index) and a memory-dir-scoped `can_use_tool` gate (read-only list/read/search + writes confined to `memory_dir`; `max_turns ≈ 20`).
  2. Deterministic fallback (MockProvider / no provider) does Jaccard dedup of near-identical entries (keep newest, conservative high threshold) + mtime-based prune. Reuse `MemorySelector` from `memory.py` for Jaccard scoring.
  3. Returns frozen `DreamResult(merged, pruned, runs, written_paths)`. All writes via `ProjectMemory.save/delete` (secret + path-traversal guards intact).
  4. Idempotent: a second dream over an already-consolidated store is a no-op (`merged=0, pruned=0`).
  5. Gating reuses M5's `consolidation_lock.should_dream(...)` — M6 does NOT re-implement gating.
  6. `tests/test_dream_consolidator.py` passes ≥10 cases. pytest grows by ≥10.

- **how M6 calls the gate cascade (M5 rollback contract)**:
  ```python
  decision = should_dream(lock_path, sessions_dir, enabled=True, now_ms=..., last_scan_at_ms=...)
  if not decision.should_dream:
      return DreamResult(merged=0, pruned=0, runs=0, written_paths=[])
  try:
      # run 4-stage ForkedAgentRunner here
      ...
  except Exception:
      rollback_consolidation_lock(lock_path, decision.prior_mtime)
      raise
  ```
  `decision.prior_mtime` is 0.0 when there was no prior lock file; `rollback_consolidation_lock` handles this correctly (unlinks). Never call acquire separately — `should_dream` already acquired.

- **relevant files for M6**:
  - CREATE: `src/simple_coding_agent/dream.py` (`DreamConsolidator`, `DreamResult`)
  - CREATE: `tests/test_dream_consolidator.py`
  - READ (do not modify): `src/simple_coding_agent/consolidation_lock.py` — gating entry point
  - READ (do not modify): `src/simple_coding_agent/forked_agent.py` — M1's `ForkedAgentRunner` for the LLM path
  - READ (do not modify): `src/simple_coding_agent/memory.py` — `MemorySelector` for Jaccard dedup, `ProjectMemory.save/delete` for guarded writes
  - READ: TS source `autoDream/consolidationPrompt.ts:10` (`buildConsolidationPrompt` — port 4-phase prompt AND anti-turn-waste directives verbatim in spirit), `extractMemories/extractMemories.ts:171` (`createAutoMemCanUseTool` — the memory-dir gate to mirror)

- **expected tests** (`tests/test_dream_consolidator.py`, ≥10 cases):
  - Deterministic fallback: Jaccard dedup merges near-identical entries
  - Deterministic fallback: mtime-based prune removes oldest below threshold
  - Idempotency: second run over already-consolidated store → merged=0, pruned=0
  - LLM path (MockProvider scripted): 4-stage prompt delivered to ForkedAgentRunner; writes confined to memory_dir (can_use_tool gate blocks writes outside)
  - Rollback: if ForkedAgentRunner raises, rollback_consolidation_lock is called with decision.prior_mtime
  - Gate: when should_dream returns False, DreamResult is a no-op (merged=0, pruned=0, no lock held)
  - Secret guard: ProjectMemory.save rejects memory bodies matching the secret pattern
  - Path-traversal guard: ProjectMemory.save blocks paths escaping memory_dir

- **risks for M6**:
  - **mtime resolution gotcha (from M5)**: `os.utime` takes float seconds; `os.stat().st_mtime` returns float seconds. Round-trip through division/multiplication by 1000 can introduce sub-millisecond drift. In tests, allow ±1 second tolerance in mtime comparisons (all M5 tests already do this — follow the same pattern).
  - **`os.utime` second-vs-ms conversion**: M5's `rollback_consolidation_lock` converts `prior_mtime` (ms) to seconds via `prior_mtime / 1000.0` before calling `os.utime`. M6 must pass `prior_mtime` in the same ms unit (as returned by `try_acquire_consolidation_lock` and `DreamGateDecision.prior_mtime`).
  - **PID-reuse guard edge case**: A lock older than HOLDER_STALE_MS is always reclaimed regardless of PID liveness (autoDream.ts:60 `Date.now() - mtimeMs < HOLDER_STALE_MS`). M6's retry logic must not assume a held lock means the prior dream is still running — check the mtime age instead.
  - **`_force_compact` try/finally (M4 invariant)**: M6 does NOT touch `_force_compact`. Keep the invariant in mind — the M4 `reused=` emit fires before `record_full_compact()` and before the try/finally restore. Don't change this order.
  - **ForkedAgentRunner max_turns ≈ 20**: The 4-stage consolidation prompt is more complex than the 5-turn extraction prompt. Use `max_turns=20` or a config kwarg — do not hardcode 5 from `ExtractMemoriesRunner`.
