# HANDOFF — session-memory-dream (M2 done, next: M3)

> Updated by: M2 milestone agent
> Date: 2026-06-15
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `session-memory-dream`
- **current milestone**: M2 — done
- **next milestone**: `M3` — loop wiring + LLM updater + session_store round-trip
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [next], M4 [pending], M5 [pending], M6 [pending], M7 [pending]

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
  - `merge logic is simple overwrite-then-fallback`: `update_session_memory` takes new content from new_messages; if a section has no new content, falls back to the previous state's value. There's no cross-turn accumulation within a section (e.g. "append new user messages to All User Messages"). M3's LLM updater will handle richer merging.

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `(see git log)` — `[sm-dream/M2] add SessionMemoryState + incremental fold + SessionMemorySummarizer`
- **tests**: 951 passing (+1 xpassed)
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
  - `update_session_memory(state, new_messages) -> SessionMemoryState` — pure function, immutable, no side effects. M3 is the PRODUCER (calls this per-turn). Do NOT change the signature.
  - `SessionMemorySummarizer` (compact.py): `__init__(state, fallback=None)` + `.summarize(messages) -> str` implementing the `Summarizer` Protocol drop-in. Do NOT change these signatures.
  - `SessionMemoryState.to_jsonable()` is the on-disk shape that M3's `session_store` round-trip must consume. M3 must keep it backward-compatible (new keys in to_jsonable output must be tolerated by from_jsonable via the unknown-key-ignore path).
  - `ContextCompactor`, `CompactSummary`, the `Summarizer` Protocol, `RuleBasedSummarizer`, `LLMSummarizer`, and `MicroCompactor` in `compact.py` are byte-identical in behavior — M2 only ADDED `SessionMemorySummarizer` and one import. Do not change any existing compact.py class signatures.

## 5. Next milestone guidance

For `M3` — loop wiring + LLM updater + session_store round-trip:

- **next scope**: Wire M2's producer/consumer into the runtime. Specifically:
  1. **`loop.py::_run_stop_hooks`** — call `update_session_memory(self._session_memory_state, new_messages)` per-turn when `--session-memory` flag is set; store result in a new `_session_memory_state` field on `AgentLoop`.
  2. **`loop.py::_force_compact`** — inject `SessionMemorySummarizer(self._session_memory_state, fallback=RuleBasedSummarizer())` as the summarizer when `_force_compact` calls `ContextCompactor`. On a WARM state, compaction costs O(0) provider calls.
  3. **`session_store.py` round-trip** — persist `session_memory_state` alongside the transcript in the session JSON: `state.to_jsonable()` on save, `SessionMemoryState.from_jsonable(...)` on load (unknown-key-ignore is already implemented — just call it). The key in the JSON envelope should be `"session_memory_state"` (absent → `SessionMemoryState.empty()`).
  4. **CLI `--session-memory` flag** — add to both `cli.py` and `openai_cli.py`; default OFF. When ON: create `SessionMemoryState.empty()` at loop construction; wire it through `_run_stop_hooks` and `_force_compact`.
  5. **LLM updater via `ForkedAgentRunner`** — optionally, replace the `RuleBasedSummarizer().summarize()` call inside `update_session_memory` with an LLM-backed updater using `ForkedAgentRunner(provider, sm_system_prompt, can_use_tool=lambda *_: (True, ""), tool_registry=empty_registry)` and the SM update prompt from `prompts.ts`. This is M3's core new feature (the "dream" in session-memory-dream). The LLM receives the current `state.render()` + new messages and returns updated section text.

- **relevant files**:
  - MODIFY: `src/simple_coding_agent/loop.py` — add `_session_memory_state: SessionMemoryState` field; wire into `_run_stop_hooks` and `_force_compact`.
  - MODIFY: `src/simple_coding_agent/session_store.py` — add `session_memory_state` key to the session JSON envelope (`SessionMemoryState.to_jsonable()` / `from_jsonable()`).
  - MODIFY: `src/simple_coding_agent/cli.py` — add `--session-memory` flag; pass state into AgentLoop.
  - MODIFY: `src/simple_coding_agent/openai_cli.py` — same flag.
  - READ (do NOT modify): `src/simple_coding_agent/session_memory_state.py` — M2's `update_session_memory` is the PRODUCER that M3 wires; `SessionMemoryState.from_jsonable` is what M3's session_store must call on load.
  - READ (do NOT modify): `src/simple_coding_agent/compact.py` — `SessionMemorySummarizer` is already there; M3 just needs to inject it at `_force_compact` time with the current `_session_memory_state`.
  - READ (do NOT modify): `src/simple_coding_agent/forked_agent.py` — M3's LLM updater uses `ForkedAgentRunner`; see M1 HANDOFF for the exact constructor signature.

- **expected tests**:
  - NEW: `tests/test_loop_session_memory.py` — AgentLoop integration: `--session-memory` ON produces a WARM state after 1+ turns; warm state yields O(0) compaction in subsequent compact calls.
  - EXTEND: `tests/test_end_to_end_long_session.py` — scenario where SM state survives a `/save`+`/load` round-trip via session_store.
  - EXTEND: `tests/test_repl_save_load.py` — `/save` includes `session_memory_state` key; `/load` restores it.

- **risks and things M3 should watch for**:
  - **`update_session_memory` receives ONLY new messages** (not the full transcript): M3 must decide the slice — likely messages since the last `_session_memory_update_cursor` (a new `uuid` cursor that M3 should store on AgentLoop alongside `_session_memory_state`). The cursor advances after each successful `update_session_memory` call.
  - **warm/cold detection is `is_warm` on the state**: if the cursor is at the start of the session, `is_warm` is False (cold) and the fallback fires. After the first fold, `is_warm` is True and subsequent compactions are O(0). Make sure the first-turn update actually produces a warm state (non-empty messages required — watch for turns where the only messages are attachments or virtual messages).
  - **`from_jsonable` contract for session_store**: M3 must use `SessionMemoryState.from_jsonable(data.get("session_memory_state", {}))` — the `{}` default is safe because `from_jsonable({})` → `empty()` (the missing-sections → empty path is tested and confirmed working).
  - **compact.py line count**: compact.py is now 655 lines (was 617, added 38 for `SessionMemorySummarizer`). M3 must NOT add new classes to compact.py without checking the ≤800 line limit.
  - **LLM updater prompt**: Use `DEFAULT_SESSION_MEMORY_TEMPLATE` from `src/services/SessionMemory/prompts.ts:11-41` as the system context. The 10-heading TS template is for the LLM updater; the 9-section Python section set is for the deterministic fold. Decide in M3 whether to keep one unified section set or keep them separate. If unified (recommended), migrate `_SECTION_NAMES` in `session_memory_state.py` to the 10 TS headings and update the parser accordingly — but that's a HANDOFF §2 deviation that must be documented.
