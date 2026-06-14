# HANDOFF — session-memory-dream (M4 done, next: M5)

> Updated by: M4 milestone agent
> Date: 2026-06-15
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `session-memory-dream`
- **current milestone**: M4 — done
- **next milestone**: `M5` — consolidation_lock + faithful dream gate cascade
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [done], M5 [next], M6 [pending], M7 [pending]

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

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `(see git log)` — `[sm-dream/M4] SM-compact observability + dual-arm latency benchmark`
- **tests**: 969 passing (+1 xpassed)
- **mypy**: clean (`mypy src` → no issues in 32 source files)
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
  - `load_session` now returns 3-tuple `(Transcript, CompactSummary | None, SessionMemoryState)`. All callers that previously used 2-tuple destructuring have been updated. M5 must not revert to 2-tuple.
  - Two-tier null-vs-throw compaction contract: cold SM falls through to configured summarizer, NEVER crashes `_force_compact`. M5 must not break `_force_compact`'s try/finally structure.
  - `ContextCompactor.summarizer` is temporarily mutated in `_force_compact` (try/finally). Must be preserved in all future modifications to `_force_compact`.
- **invariants added by M4**:
  - `MetricsCollector.sm_compact_reuses` and `MetricsCollector.sm_compact_misses` counter names are FROZEN — later milestones must not rename them (the `/stats` REPL command exposes them in `format_stats()`).
  - `reused=<bool>` field on the `compact` trace channel is FROZEN — it appears in the second trace emit from `_force_compact`. Later milestones must not remove or rename this field.
  - `benchmarks/_results/04_sm_compact_latency.{json,md}` are committed artifacts; they represent the deterministic floor at time of M4 commit. The honesty rule stands: never conflate deterministic numbers with real-API numbers.
  - No fabricated percentages: the benchmark must always report measured `perf_counter` timings with `latency_source` attribution. Never hardcode a ratio or percentage.

## 5. Next milestone guidance

For `M5` — consolidation_lock + faithful dream gate cascade:

- **next scope** (from PLAN.md M5):
  1. New `src/simple_coding_agent/consolidation_lock.py` replicating the cheapest-first dream gate cascade:
     - `read_last_consolidated_at()` — reads lock file mtime as `datetime | None`
     - `list_sessions_touched_since(sessions_dir, since_dt)` — scans session files by mtime
     - `try_acquire_consolidation_lock(lock_path)` — writes PID to `.consolidate-lock`, returns prior mtime or None if already held
     - `rollback_consolidation_lock(lock_path, prior_mtime)` — rewrites mtime so the time gate re-opens after failure
     - `should_dream(sessions_dir, lock_path, *, ...)` — full gate cascade: enabled → time gate (≥24h since mtime) → scan throttle (10min) → session gate (≥5 sessions since last consolidation, current excluded) → acquire lock
  2. Lock file `.consolidate-lock` is BOTH the PID mutex AND the timing state (mtime == lastConsolidatedAt). No separate state file.
  3. HOLDER_STALE_MS = 1h (stale lock → re-acquire).
  4. All timestamps injected via `os.utime` + `monkeypatch` in tests — NO real `sleep`.
  5. `tests/test_consolidation_lock.py` passes with ≥8 cases.

- **M5 is the start of the D-line** (D1). It does NOT depend on M2/M3/M4 directly — only M1 (ForkedAgentRunner) is a dependency (for M6, not M5 itself). M5 is pure lock + gate infrastructure.

- **relevant files for M5**:
  - CREATE: `src/simple_coding_agent/consolidation_lock.py`
  - CREATE: `tests/test_consolidation_lock.py`
  - READ first: `session_store.py::resolve_sessions_dir` and `SIMPLE_AGENT_SESSIONS_DIR` — M5's `list_sessions_touched_since` reuses this resolution helper to find the sessions directory where `.json` session files live.
  - READ: TS source `autoDream/consolidationLock.ts` lines 29 (`readLastConsolidatedAt`), 46 (`tryAcquireConsolidationLock`), 91 (`rollbackConsolidationLock`), 118 (`listSessionsTouchedSince`); and `autoDream/autoDream.ts` lines 63-66 (DEFAULTS: minHours=24, minSessions=5), 56 (SESSION_SCAN_INTERVAL_MS=10min), 95 (isGateOpen), 125 (runAutoDream gate order).

- **expected tests** (`tests/test_consolidation_lock.py`, ≥8 cases):
  - Time gate OPEN when lock file mtime > 24h ago
  - Time gate CLOSED when lock file mtime < 24h ago
  - Session gate passes when ≥5 sessions touched since lastConsolidatedAt (current session excluded)
  - Session gate fails when <5 sessions touched
  - Scan-throttle blocks re-scan within 10min
  - `try_acquire_consolidation_lock` returns prior mtime when acquired; None when already held by live PID
  - `rollback_consolidation_lock` rewinds mtime so time gate re-opens
  - `mtime == lastConsolidatedAt` round-trip (write lock → read mtime → verify datetime matches)
  - All timestamps injected via `os.utime(path, (access_time, mtime))` + `monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))`

- **risks for M5**:
  - **Stale lock detection**: The TS uses `HOLDER_STALE_MS=1h` to detect dead-PID lock holders. In tests, inject a lock file with a PID that doesn't exist (e.g. `os.getpid() + 99999`) and an old mtime — the acquire function should treat it as stale and re-acquire. This is the trickiest test case.
  - **Platform differences in `os.utime`**: `os.utime` takes `(atime_ns, mtime_ns)` or `(atime, mtime)` in seconds — use the float form and verify with `os.stat(path).st_mtime` round-trip. Sub-second precision may differ on macOS vs Linux.
  - **`list_sessions_touched_since` current-session exclusion**: The TS excludes the current session from the count. The replica analog is "exclude the file being written to right now" — but since M5 is CLI-driven, the current session may not be identifiable. A safe default: pass the current session's path as an optional `exclude_path` arg and skip it in the scan.
  - **`_force_compact` try/finally (from M4 invariant)**: M5 doesn't touch `_force_compact`, but keep the invariant in mind — the M4 `reused=` emit now fires BEFORE `record_full_compact()` and BEFORE the try/finally restore. Don't change this order.
