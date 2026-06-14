# HANDOFF — session-memory-dream (M3 done, next: M4)

> Updated by: M3 milestone agent
> Date: 2026-06-15
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `session-memory-dream`
- **current milestone**: M3 — done
- **next milestone**: `M4` — SM-compact observability + dual-arm latency benchmark
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [next], M5 [pending], M6 [pending], M7 [pending]

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

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `(see git log)` — `[sm-dream/M3] wire session-memory into loop + LLM updater + cross-process persistence`
- **tests**: 962 passing (+1 xpassed)
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
  - `load_session` now returns 3-tuple `(Transcript, CompactSummary | None, SessionMemoryState)`. All callers that previously used 2-tuple destructuring have been updated. M4 must not revert to 2-tuple.
  - Two-tier null-vs-throw compaction contract: cold SM falls through to configured summarizer, NEVER crashes `_force_compact`. M4's observability wiring touches `_force_compact` — do not break this.
  - `ContextCompactor.summarizer` is temporarily mutated in `_force_compact` (try/finally). M4 must not change `_force_compact`'s try/finally structure without preserving the fallback guarantee.

## 5. Next milestone guidance

For `M4` — SM-compact observability + dual-arm latency benchmark:

- **next scope** (verbatim from PLAN.md M4):
  1. `MetricsCollector` gains `sm_compact_reuses` and `sm_compact_misses` (`record_*` methods + `format_stats` lines) surfaced via `/stats`.
  2. Emit `reused=<bool>` on the EXISTING `compact` trace channel — NO new channel (11-name vocab frozen). Assert the `StderrTracer` line contains `reused=True`/`reused=False`.
  3. New `benchmarks/bench_sm_compact_latency.py` — headless, writes `benchmarks/_results/04_sm_compact_latency.{json,md}`, two arms: (a) DETERMINISTIC (RuleBasedSummarizer vs O(0) SM reuse, no API), (b) REAL-API gated behind `--confirm-api-call`.
  4. `tests/test_bench_sm_compact.py` asserts `measured_reuse_ms < full_arm_ms` with injected delay.

- **where to observe the reuse/miss decision**: `loop.py::_force_compact` lines ~694-708. The branch `if self._sm_enabled and self._session_memory_state.is_warm:` is the reuse decision point. M4 should record `sm_compact_reuses` in the True branch and `sm_compact_misses` in the else branch, then emit `reused=<bool>` on the `compact` trace channel BEFORE or AFTER the existing `compact` emit inside `ContextCompactor.compact()` — or pass `reused` as a kwarg to the trace emit that already fires inside `ContextCompactor.compact()`. The cleanest approach: add `reused` to the `ContextCompactor.compact()` trace emit by passing it as a parameter from `_force_compact` — but that requires changing `compact.py`. Alternatively, add a second `tracer.emit("compact", reused=...)` in `_force_compact` after the compaction. The 11-channel constraint allows multiple emits on the same channel.

- **relevant files for M4**:
  - MODIFY: `src/simple_coding_agent/metrics.py` — add `sm_compact_reuses: int = 0`, `sm_compact_misses: int = 0`, `record_sm_compact_reuse()`, `record_sm_compact_miss()`, update `format_stats()`.
  - MODIFY: `src/simple_coding_agent/loop.py::_force_compact` — call `self._metrics.record_sm_compact_reuse()` or `record_sm_compact_miss()`, emit `reused=<bool>` on `compact` trace channel.
  - NEW: `benchmarks/bench_sm_compact_latency.py` — two-arm benchmark.
  - NEW: `tests/test_bench_sm_compact.py` — CI-fast timing assertion.
  - ALSO CHECK: `tests/test_trace.py` — the frozen trace channel test; confirm `compact` channel is already listed; M4 adds `reused` FIELD to an existing channel (not a new channel name), which is safe.

- **expected tests** (per PLAN exit gate, pytest grows ≥7):
  - `tests/test_bench_sm_compact.py` — `measured_reuse_ms < full_arm_ms` (injected delay), metrics counter assertions, trace `reused=` field.
  - Metrics counter integration tests — reuse/miss counters bump in correct branch.

- **risks for M4**:
  - **NO-ASYNC DIVERGENCE** (document for final review Current Limitations): TS background SM extraction (query.ts:1001 `void executePostSamplingHooks`) → replica SYNCHRONOUS incremental fold at stop hook. This is already documented in `extraction_hooks.py` module header. The final review session must fold this into `CLAUDE.md` Current Limitations. The final review agent should look in `extraction_hooks.py` module docstring for the exact wording.
  - **`update_session_memory_llm` not wired into stop-hook**: The LLM-mode updater exists in `session_memory_state.py` but `maybe_update_session_memory` calls the deterministic fold only. If M4 or a future milestone wants to opt into LLM updates per turn, they must add a flag like `--session-memory-mode llm` and plumb it through `maybe_update_session_memory`. This was a conscious M3 decision (see §2 Known Limitations above).
  - **benchmark honesty**: Never reintroduce a fabricated percentage. Every benchmark number must disclose its source. The PLAN's honesty rules apply: deterministic arm = reproducible floor; real-API arm = realistic headline; both labeled, never conflated.
  - **trace channel freeze**: The `compact` channel already has `messages`, `post_tokens`, `pre_tokens`, `summarized` fields. Adding `reused=<bool>` is additive (not a new channel). The test `test_nine_channel_format_unchanged_for_scalar_values` pins specific field values for existing channels — M4 must NOT change existing field values, only add `reused`.
