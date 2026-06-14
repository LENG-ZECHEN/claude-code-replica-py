# HANDOFF — session-memory-dream (M1 done, next: M2)

> Updated by: M1 milestone agent
> Date: 2026-06-15
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `session-memory-dream`
- **current milestone**: M1 — done
- **next milestone**: `M2` — SessionMemoryState + incremental fold + SessionMemorySummarizer
- **all milestones (per PLAN)**: M1 [done], M2 [next], M3 [pending], M4 [pending], M5 [pending], M6 [pending], M7 [pending]

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

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `(see git log)` — `[sm-dream/M1] extract ForkedAgentRunner from ExtractMemoriesRunner`
- **tests**: 923 passing (+1 xpassed)
- **mypy**: clean (`mypy src` → no issues in 31 source files)
- **ruff**: clean (`ruff check .` → All checks passed!)
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: `forked_agent.py::ForkedAgentRunner` public contract (below) — M3 and M6 build on it.
- **frozen public contracts (added by M1)**:
  - `ForkedAgentRunner.__init__(provider, system_prompt, can_use_tool, tool_registry, max_turns=10)` + `.run(task_prompt: str, context_messages: list[dict] = ()) -> ForkedAgentResult` — consumed by M3 (SM LLM updater) and M6 (dream engine). Do not change these signatures.
  - `ExtractMemoriesRunner.__init__(provider, memory_dir, system_prompt, base_messages, tool_registry)` and `.run(new_message_count) -> ExtractionResult` (frozen dataclass) — consumed by `extraction_hooks.py`. Keep byte-identical.
  - `ExtractionResult(written_paths, errors, turn_count)` — frozen; `extraction_hooks.py` pattern-matches on these fields.
  - Gate semantics: deny → `(reason, True)` returned as tool_result content BEFORE executor/registry; no schema filter. Mirrors plan-mode soft-deny invariant.
- **preserve**: the 11-name trace channel vocabulary in `trace.py` is FROZEN and test-pinned — do NOT add a new channel (SM-compact reuses `compact`; dream surfaces via metrics + CLI, not a new channel).
- **compatibility requirements**: `session_store.py` JSON envelope changes must be backward-compatible (new keys optional; absent → empty/default), mirroring how `restored_files`/`timestamp` are already optional.

## 5. Next milestone guidance

For `M2` — SessionMemoryState + incremental fold + SessionMemorySummarizer:

- **next scope**: M2 is abstraction + unit tests only — NO loop wiring, NO session_store, NO CLI (those are M3). Build two things: (1) `SessionMemoryState` (new `session_memory_state.py`) — a frozen dataclass holding a running 9-section summary with `to_jsonable()/from_jsonable()` round-trip including unknown-key forward-compat, and a pure function `update_session_memory(state, new_messages) -> NEW state` (immutable — input unchanged). (2) `SessionMemorySummarizer` — implements the `Summarizer` Protocol from `compact.py`: WARM state → returns prewarmed text with ZERO provider calls; COLD/empty state → delegates to a configured fallback (`RuleBasedSummarizer` or `LLMSummarizer`). A `ContextCompactor(summarizer=SessionMemorySummarizer(prewarmed))` should produce a valid `CompactSummary` with non-empty `summary_text`. M2 does NOT depend on M1 (the deterministic fold and the Summarizer Protocol are independent of `ForkedAgentRunner`).
- **relevant files**:
  - NEW: `src/simple_coding_agent/session_memory_state.py`
  - READ: `src/simple_coding_agent/compact.py` — the `Summarizer` Protocol (the interface `SessionMemorySummarizer` must implement) + `ContextCompactor` + `CompactSummary`; the 9-section extraction in `RuleBasedSummarizer._extract_sections` is the heuristic to reuse for the deterministic fold
  - READ: `sessionMemoryCompact.ts:58-60` `DEFAULT_SM_COMPACT_CONFIG` (minTokens=10_000, minTextBlockMessages=5, maxTokens=40_000) and `SessionMemory/prompts.ts:11-41` `DEFAULT_SESSION_MEMORY_TEMPLATE` (the 9 section names + header/italic instruction lines are load-bearing)
  - DO NOT TOUCH: `compact.py`, `loop.py`, `session_store.py`, `extract_memories.py`, `forked_agent.py`
- **expected tests**: `tests/test_session_memory_state.py`, `tests/test_session_memory_summarizer.py` (≥12 new cases total)
- **risks**:
  - **Context injection semantics to watch (M3 consumer)**: `ForkedAgentRunner.run()` prepends `context_messages` as a list and appends `{"role": "user", "content": task_prompt}`. If the slice ends with a user message, there will be two consecutive user messages before the first provider call. OpenAI Chat Completions allows consecutive same-role messages so this is safe; DashScope behavior should be verified by M3. The M6 (dream) consumer passes `context_messages=()` so it is unaffected.
  - **`update_session_memory` immutability**: Must return a NEW `SessionMemoryState` — the pure-function pattern is the invariant. Input `state` must not be mutated (matches the project-wide immutability rule and the frozen dataclass design).
  - **forward-compat in `from_jsonable`**: Unknown keys in the JSON must be silently ignored (same pattern as `session_store.py` round-trip). This is required so old session files with newer SM-state formats can still load.
