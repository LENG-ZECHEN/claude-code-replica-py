# HANDOFF — Next: M7 (sidequery-recall-and-injection)

> Updated by: M6 execution (auto-mem/M6 session)
> Date: 2026-05-24
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `auto-memory-overhaul`
- **current milestone**: just-completed `M6` — provider-selector-and-memdir-infra
- **next milestone**: `M7` — sidequery-recall-and-injection
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [done], M5 [done], M6 [done], M7 [next]

## 2. Completed milestones

### M1

- **commit**: `612487d` — `[auto-mem/M1] .md frontmatter format, scan, migrate-format CLI`
- **files changed**: `memory.py`, `memory_cli.py`, `test_memory_frontmatter.py`, `test_memory_manifest_format.py`, `test_memory_scan_recursive.py`, `test_memory_migrate.py`
- **tests added**: `test_memory_frontmatter.py` (+4), `test_memory_manifest_format.py` (+4), `test_memory_scan_recursive.py` (+3), `test_memory_migrate.py` (+2). Total: 711 → 724 (+13)
- **behavior implemented**: `ProjectMemory.save()` writes `<id>.md` with YAML frontmatter. `scan_memory_files(dir)` recursively returns `MemoryHeader[]` ordered by mtime desc. `MEMORY.md` manifest with 200-line + 25KB truncation. `simple-agent memory migrate-format` converts `.json` → `.md` idempotently. Dual-read compat in `all()` and `load()`.
- **design decisions (deviations from PLAN)**:
  - (none)
- **known limitations**:
  - (none)

### M2

- **commit**: `[auto-mem/M2]` (see git log)
- **files changed**: `coding_tools.py`, `loop.py`, `tests/test_write_memory_tool.py`
- **tests added**: `test_write_memory_tool.py` (+10 cases). Total: 724 → 734 (+10)
- **behavior implemented**: `coding_tools.write_memory_entry(project_memory, type, id, name, description, body, tags=None)` validates type ∈ {user, feedback, project, reference}, id against `_SAFE_ENTRY_ID_PATTERN`, description ≤ 150 chars, and body against `_check_body_for_secrets`, then calls `project_memory.save(entry)`. Exported in `coding_tools.__all__`. `AgentLoop` gains `_memory_writes_this_turn: int = 0` (reset at the start of each `run()` / `run_stream()`). `_register_tools()` registers `write_memory_entry` in the loop's registry only when `project_memory is not None`; the tool closure captures `self` to enforce the per-turn quota of 3 (4th write returns `"memory write quota exhausted this turn (max 3)"` as `is_error=True`). Upsert semantics: calling with an existing `id` overwrites the `.md` file via `project_memory.save()`.
- **design decisions (deviations from PLAN)**:
  - **Inline closure in `_register_tools` instead of standalone `register_write_memory_entry_tool`**: The PLAN notes proposed a separate `register_write_memory_entry_tool(registry, project_memory)` function mirroring `register_snip_history_tool`. Instead, the registration is an inline closure inside `AgentLoop._register_tools()`. This is because the closure needs access to `self._memory_writes_this_turn` for quota reset (capturing `self` is the simplest approach — no separate mutable container needed). Visible in: `loop.py:_register_tools`. Impact on M3: none — M3 can call `_register_tools` is not exposed externally; M3 wires `ProjectMemory` into the system prompt, not the tool registration.
- **known limitations**:
  - (none)

### M3

- **commit**: `[auto-mem/M3]` (see git log)
- **files changed**: `context.py`, `cli.py`, `tests/test_loop_memory_prompt.py`, `tests/test_loop_write_memory_e2e.py`
- **tests added**: `test_loop_memory_prompt.py` (+3), `test_loop_write_memory_e2e.py` (+2). Total: 734 → 739 (+5)
- **behavior implemented**: `ContextBuilder.__init__` gains `project_memory: ProjectMemory | None = None`. `_MEMORY_MANAGEMENT_SECTION` is a module-level string constant (~250 tokens, fully static). `ContextBuilder._build_system_prompt()` inserts this section between the CLAUDE.md/base section and the `## Memory` snippets block when `project_memory is not None`. `cli.py`'s `_build_repl_loop` now passes `project_memory=project_memory` to `ContextBuilder`. `openai_cli.py` needed no change — it routes through `_cli._build_repl_loop`.
- **design decisions (deviations from PLAN)**:
  - **`openai_cli.py` unchanged**: PLAN listed it as a file to touch, but it already routes everything through `_cli._build_repl_loop`. The fix in `_build_repl_loop` propagates automatically. No separate change needed.
- **known limitations**:
  - (none)

### M4

- **commit**: `[auto-mem/M4]` (see git log)
- **files changed**: `extract_memories.py` (new), `tests/test_extract_memories_runner.py` (new)
- **tests added**: `test_extract_memories_runner.py` (+11 cases). Total: 739 → 750 (+11)
- **behavior implemented**: New module `src/simple_coding_agent/extract_memories.py` with three public exports: `ExtractionResult(frozen=True)` dataclass with fields `(written_paths: tuple[str, ...], errors: tuple[str, ...], turn_count: int)`; `build_extract_prompt(new_message_count, existing_memories_manifest) -> str` free function producing the 5-section prompt (opener / immediate action / types / what-not-to-save / how-to-save); `ExtractMemoriesRunner(provider, memory_dir, system_prompt, base_messages, tool_registry)` with `.run(new_message_count) -> ExtractionResult`. The runner inner loop calls provider up to MAX_TURNS=5 times, enforces the tool whitelist `{read_file, list_files, search_text, write_memory_entry}` via `_execute_tool()` dispatcher, creates a local `ProjectMemory(memory_dir)` for `write_memory_entry` (not the main agent's), and uses `for/else` to append `"max turns reached"` when all 5 turns exhaust without an end_turn. `_get_existing_manifest` is an M4 stub reading `MEMORY.md[:2000]` or returning `"(no memories yet)"`. `base_messages` is copied at construction (`list(base_messages)`) but NOT injected into the inner provider calls in M4 (the inner loop starts fresh from the extraction prompt alone).
- **design decisions (deviations from PLAN)**:
  - **`base_messages` typed as `list[dict[str, Any]]` not `list[Message]`**: The PLAN spec said `list[Message]`, but the runner never uses `base_messages` in M4's provider calls and the dict form matches how messages actually flow through the system. Simpler tests (no need to import/construct Message objects). Impact on M5: M5 must construct the runner passing dict messages (the serialized form from Transcript), not raw Message objects.
  - **`_executor = ToolExecutor(tool_registry)` in constructor**: Runner creates a private `ToolExecutor` from the registry rather than calling `tool_registry.execute()` directly (that method doesn't exist — only `ToolExecutor.execute()` does). Impact on M5: pass a `ToolRegistry` with the relevant tools pre-registered.
- **known limitations**:
  - `_get_existing_manifest` is a stub (reads MEMORY.md[:2000]). M6 replaces it with `format_memory_manifest(scan_memory_files(memory_dir))`. M7 wires it as the canonical call.

### M5

- **commit**: `[auto-mem/M5]` (see git log)
- **files changed**: `extraction_hooks.py` (new), `loop.py` (modified, 788 lines),
  `metrics.py` (modified), `cli.py` (modified), `openai_cli.py` (modified),
  `tests/test_has_memory_writes_since.py` (new, 7 tests),
  `tests/test_extract_memories_gating.py` (new, 8 tests),
  `tests/test_extract_memories_e2e.py` (new, 3 tests)
- **tests added**: 18 new tests. Total: 750 → 768 (+18)
- **behavior implemented**: `extraction_hooks.py` introduces `ExtractionHookOutcome`
  (frozen dataclass), `hasMemoryWritesSince(messages, since_uuid)`, and
  `maybe_extract_memories(**kwargs)` with 7-layer gating. `AgentLoop._run_stop_hooks`
  is the single choke-point called before every return in `run()` and every yield in
  `run_stream()`; it increments `_turns_since_last_extraction` and calls
  `maybe_extract_memories`. Cursor (`_last_memory_message_uuid`) advances on success,
  is preserved on exception (at-least-once semantics). `MetricsCollector` gains
  `extract_invocations` and `extract_writes`. Both CLIs gain `--extract-memories`
  (default off) and `--extract-throttle N` (default 1), resolvable via env vars
  `SIMPLE_AGENT_EXTRACT_MEMORIES` and `SIMPLE_AGENT_EXTRACT_THROTTLE`.
- **design decisions (deviations from PLAN)**:
  - **`extraction_hooks.py` extracted from `loop.py`**: PLAN proposed adding
    `_maybe_extract_memories` and `hasMemoryWritesSince` directly to loop.py, but loop.py
    was already at 895 lines. Both functions live in the new module to keep loop.py ≤800
    lines (788 after trimming). Import is `from .extraction_hooks import maybe_extract_memories`.
  - **Defensive `hasattr(project_memory, "_dir")` check**: Pre-existing tests use
    `_RecordingProjectMemory` mock objects without `_dir`. The `_memory_dir` field is set
    only when the real `_dir` attribute exists; mock objects get `_memory_dir = None` and
    extraction is silently disabled (gate 3: `auto_memory_enabled = False`).
  - **`_run_stop_hooks` passes `extraction_in_progress=False` explicitly**: The flag is set
    on `self._extraction_in_progress` before the call and cleared after, but the re-entrancy
    guard is satisfied by passing `False` directly — the inner `maybe_extract_memories` call
    is not itself a subloop so the guard fires at the `self._extraction_in_progress` check
    level, not inside the function.
- **known limitations**:
  - `_get_existing_manifest` in `ExtractMemoriesRunner` is still the M4 stub (reads
    MEMORY.md[:2000]). M6 replaces it with `format_memory_manifest(scan_memory_files(memory_dir))`.

### M6

- **commit**: `[auto-mem/M6]` (see git log)
- **files changed**: `src/simple_coding_agent/provider.py`, `src/simple_coding_agent/memdir.py` (new),
  `tests/test_provider_selector.py` (new), `tests/test_memdir_scan.py` (new),
  `tests/test_memdir_manifest_format.py` (new), `tests/test_memdir_recent_tools.py` (new)
- **tests added**: 16 new tests. Total: 768 → 784 (+16)
- **behavior implemented**: `SelectorError` exception added to `provider.py`. `Provider`
  Protocol gains `call_selector(*, system, user, output_schema, max_tokens=256) -> dict`.
  `MockProvider` gains `selector_responses: list[dict] | None = None` constructor arg and
  `_selector_idx: int = 0` counter; `call_selector` returns scripted responses sequentially
  and raises `SelectorError` when exhausted. `OpenAIProvider` gains `selector_model: str =
  "gpt-4o-mini"` constructor arg; `call_selector` calls `client.chat.completions.create`
  with `response_format={"type":"json_object"}`, `temperature=0`, `max_tokens=max_tokens`,
  raises `SelectorError` on API error / malformed JSON / schema mismatch (missing required
  key). New `src/simple_coding_agent/memdir.py` re-exports `scan_memory_files`,
  `MemoryHeader`, `FRONTMATTER_MAX_LINES` from `memory.py`, and exports
  `format_memory_manifest`, `collect_recent_successful_tools`, `SELECT_MEMORIES_SYSTEM_PROMPT`.
  `format_memory_manifest` renders `- [name](id.md) — description` lines capped at 200,
  appends a WARNING footer when truncated. `collect_recent_successful_tools` reverse-scans
  messages from end until a USER text message (real human turn), correlates ToolCall.id to
  ToolResult.tool_use_id, returns names where is_error is explicitly False.
- **design decisions (deviations from PLAN)**:
  - **`scan_memory_files` re-exported, not reimplemented**: PLAN noted memdir.py can
    re-export from memory.py. Chose re-export to avoid duplication. Visible in:
    `memdir.py:__all__`. Impact on M7: import from `memdir` works identically.
  - **`SELECT_MEMORIES_SYSTEM_PROMPT` stored as concatenated string literals**: The
    verbatim text from TS lines 18-24 is reconstructed as Python string concatenation to
    avoid long-line ruff violations while keeping the exact content identical. The string
    content is byte-identical to the TS source.
- **known limitations**:
  - (none)

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `[auto-mem/M6]` — `git -C python-replica log --oneline -1`
- **tests**: 784 passing (was 768 after M5, delta +16)
- **mypy**: clean | **ruff**: clean
- **branch**: main
- **known failing checks**: `test_null_tracer_zero_overhead` — pre-existing before this initiative, not a regression

## 4. Important constraints (carried forward)

- **dual-read compat window**: `ProjectMemory.all()` and `load()` MUST continue reading legacy `.json` files until the migrate-format pass is run. Do not remove the `.json` fallback path until an explicit retirement milestone.
- **no PyYAML dependency**: frontmatter parsing stays hand-rolled (`_parse_frontmatter`); fail-soft (broken frontmatter yields `MemoryHeader(description=None)`, never raises).
- **atomic manifest writes**: `_update_manifest` uses `tempfile.mkstemp` + `os.replace`. Do not revert to direct open/write.
- **path traversal defense**: `_SAFE_ENTRY_ID_PATTERN` allows `/` for subdir IDs but excludes `.` — `Path.is_relative_to(root)` is the second gate. Both layers must be preserved in M7+.
- **secret rejection**: `_check_body_for_secrets` in `ProjectMemory.save()` must remain active and surface as `ValueError` for all callers (CLI exit code 2, tool `is_error=True`).
- **quota counter reset**: `AgentLoop._memory_writes_this_turn` is reset to `0` at the start of each `run()` / `run_stream()`. M7 must not remove or bypass this reset.
- **conditional tool registration**: `write_memory_entry` is registered in `AgentLoop._register_tools()` ONLY when `self._project_memory is not None`.
- **`_MEMORY_MANAGEMENT_SECTION` is a frozen constant**: M7's integration must NOT modify or shadow this constant; the section's byte-identical content is required for prompt-cache stability.
- **`ExtractMemoriesRunner.run()` must receive serialized dict messages**: `base_messages` is typed `list[dict[str, Any]]` (M4 deviation). Pass `self._transcript.normalize_for_api()` — not raw `Message` objects.
- **loop.py must stay ≤800 lines**: Currently 788. M7 changes to `loop.py` must account for this. If M7 adds >12 lines, extract helpers first.
- **M7 extends `memdir.py` — do not add `find_relevant_memories` or `read_memories_for_surfacing` in M6**: Those functions belong to M7. M6 only builds the infrastructure (Protocol method + memdir module).
- **M7 adds ATTACHMENT_MEMORY message type to `context.py`**: Ensure `_coalesce_same_role` is not broken by same-role adjacent messages when the new type is inserted.
- **`SelectorError` is the canonical error for call_selector failures**: M7 must import `SelectorError` from `provider.py`, not redefine it. Selector failure must fall back to Jaccard MemorySelector — never propagate SelectorError out of the AgentLoop.
- **`SELECT_MEMORIES_SYSTEM_PROMPT` is read-only**: M7 uses it as-is; do not modify or shadow it.

## 5. Next milestone guidance

For `M7` — sidequery-recall-and-injection:

- **next scope**: M7 extends `memdir.py` with `find_relevant_memories` (4-gate guard:
  auto_memory_enabled / non-empty / multi-word / session_bytes<60KB, filename validation
  against scan manifest) and `read_memories_for_surfacing` (≤200 lines + ≤4KB per file,
  staleness-aware header). `AgentLoop.run()` and `run_stream()` call these synchronously
  before `Provider.call()` and inject results as `<system-reminder>`-wrapped ATTACHMENT
  messages. Selector failure falls back to Jaccard MemorySelector; failure never raises
  out of the loop. Tracer emits on the existing `memory_select` channel.
- **relevant files**:
  - `src/simple_coding_agent/memdir.py` — extend with `find_relevant_memories` and
    `read_memories_for_surfacing`; M6 already provides the infrastructure
  - `src/simple_coding_agent/loop.py` — add sideQuery call + ATTACHMENT injection in
    `run()` and `run_stream()`; currently 788 lines (12 lines of budget before hitting cap)
  - `src/simple_coding_agent/context.py` — recognize ATTACHMENT_MEMORY sub-type;
    serialize without breaking `_coalesce_same_role`
  - `src/simple_coding_agent/provider.py` — `call_selector` and `SelectorError` already
    there from M6; M7 consumes them
  - `tests/test_sidequery_recall.py` (new)
  - `tests/test_memdir_surfacing.py` (new)
  - `tests/test_loop_memory_injection.py` (new)
- **expected tests**: ≥9 new tests covering gates (auto_memory, non-empty, multi-word,
  session_bytes), filename validation, truncation (≤200 lines + ≤4KB), fallback to Jaccard,
  and end-to-end injection into system prompt.
- **risks**:
  - **loop.py line budget is tight (788 / 800)**: If M7 needs more than 12 lines in
    loop.py, extract the sideQuery orchestration into a helper in memdir.py or a new
    `recall_hooks.py` — mirror the M5 decision to extract `extraction_hooks.py`.
  - **`_coalesce_same_role` must handle ATTACHMENT_MEMORY**: The ctx-mgmt-pdf-align
    post-review added `_coalesce_same_role`/`_merge_content` to avoid adjacent same-role
    API messages. ATTACHMENT injection adds user-role messages — verify the coalescing
    logic still handles them correctly and that the coalesced form is Anthropic-API
    compatible.
  - **`already_surfaced` set and `read_file_state` deduplication**: The session-scoped
    sets must be initialized on `AgentLoop.__init__` (not per-turn) so they persist
    across turns and avoid re-surfacing the same memory file. This adds two fields to
    `AgentLoop.__init__` which counts against the 800-line cap.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M7.md`
