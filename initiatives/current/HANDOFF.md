# HANDOFF — Next: M5 (extract-stop-hook-and-gating)

> Updated by: M4 execution (auto-mem/M4 session)
> Date: 2026-05-24
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `auto-memory-overhaul`
- **current milestone**: just-completed `M4` — extract-memories-runner
- **next milestone**: `M5` — extract-stop-hook-and-gating
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [done], M5 [next], M6 [pending], M7 [pending]

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

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `[auto-mem/M4]` — `git -C python-replica log --oneline -1`
- **tests**: 750 passing (was 739 after M3, delta +11)
- **mypy**: clean (23 source files, no issues)
- **ruff**: clean
- **branch**: main
- **known failing checks**: `test_null_tracer_zero_overhead` — pre-existing before this initiative, not a regression

## 4. Important constraints (carried forward)

- **dual-read compat window**: `ProjectMemory.all()` and `load()` MUST continue reading legacy `.json` files until the migrate-format pass is run. Do not remove the `.json` fallback path until an explicit retirement milestone.
- **no PyYAML dependency**: frontmatter parsing stays hand-rolled (`_parse_frontmatter`); fail-soft (broken frontmatter yields `MemoryHeader(description=None)`, never raises).
- **atomic manifest writes**: `_update_manifest` uses `tempfile.mkstemp` + `os.replace`. Do not revert to direct open/write.
- **path traversal defense**: `_SAFE_ENTRY_ID_PATTERN` allows `/` for subdir IDs but excludes `.` — `Path.is_relative_to(root)` is the second gate. Both layers must be preserved in M5+.
- **secret rejection**: `_check_body_for_secrets` in `ProjectMemory.save()` must remain active and surface as `ValueError` for all callers (CLI exit code 2, tool `is_error=True`).
- **quota counter reset**: `AgentLoop._memory_writes_this_turn` is reset to `0` at the start of each `run()` / `run_stream()`. M5+ must not remove or bypass this reset.
- **conditional tool registration**: `write_memory_entry` is registered in `AgentLoop._register_tools()` ONLY when `self._project_memory is not None`. M5 must pass a `ProjectMemory` instance to `AgentLoop.__init__` for the tool to be active.
- **`_MEMORY_MANAGEMENT_SECTION` is a frozen constant**: M5's integration must NOT modify or shadow this constant; the section's byte-identical content is required for prompt-cache stability.
- **M4's `ExtractMemoriesRunner` must receive a snapshot of `base_messages`**: The runner makes a `list()` copy at construction. M5's stop hook must pass a frozen snapshot (e.g., `list(transcript.to_api_messages())`) — not a live reference.
- **`ExtractMemoriesRunner.run()` does NOT set `_is_subloop` on the AgentLoop**: M5's stop hook must ensure the runner's inner call path cannot recursively trigger another extraction. The gating layer `(1) is_subloop` in `_maybe_extract_memories` is the safeguard — the runner itself has no concept of subloop state.

## 5. Next milestone guidance

For `M5` — extract-stop-hook-and-gating:

- **next scope**: Wire `ExtractMemoriesRunner` into `AgentLoop.run()` and `run_stream()` via a `_run_stop_hooks(result)` call before each method returns. The core logic lives in `_maybe_extract_memories()`, which enforces 7 gating layers in order: (1) is_subloop guard, (2) `extract_memories_enabled` flag, (3) `auto_memory_enabled`, (4) `extraction_in_progress` lock, (5) `hasMemoryWritesSince(messages, since_uuid)` check for new writes since the last extraction cursor, (6) throttle counter (`_turns_since_last_extraction`), (7) actually call `runner.run()`. The cursor `_last_memory_message_uuid` advances on success and does NOT advance on exception (at-least-once semantics). `--extract-memories` flag is exposed on both CLIs (default off, resolvable via `SIMPLE_AGENT_EXTRACT_MEMORIES` env var). `MetricsCollector` gains two new counters: `extract_invocations` and `extract_writes`.
- **relevant files**:
  - `src/simple_coding_agent/extract_memories.py` — the runner M4 delivered; M5 calls `.run()` from the stop hook
  - `src/simple_coding_agent/loop.py` — add `_run_stop_hooks`, `_maybe_extract_memories`, `_last_memory_message_uuid`, `_extraction_in_progress`, `_turns_since_last_extraction` fields + `extract_memories_enabled` / `auto_memory_enabled` constructor kwargs
  - `src/simple_coding_agent/metrics.py` — add `extract_invocations: int = 0` and `extract_writes: int = 0` to `MetricsCollector`
  - `src/simple_coding_agent/cli.py` — add `--extract-memories` flag and `_resolve_threshold`-style precedence
  - `src/simple_coding_agent/openai_cli.py` — same flag; delegates through `_cli._build_repl_loop`
  - `tests/test_extract_memories_gating.py` — new; one test per gating layer
  - `tests/test_has_memory_writes_since.py` — new; cursor logic
  - `tests/test_extract_memories_e2e.py` — new; end-to-end MockProvider driven run
- **expected tests** (≥9 per PLAN):
  - One test per each of the 7 gating layers verifying that layer short-circuits extraction
  - `hasMemoryWritesSince` with a message that has a `write_memory_entry` tool_use after the cursor → True
  - `hasMemoryWritesSince` with cursor past the message → False
  - Cursor advances on success; does NOT advance on exception
  - `extract_invocations` and `extract_writes` counters increment correctly
- **risks**:
  - `ExtractMemoriesRunner` receives `base_messages: list[dict[str, Any]]` — M4 deviated from the PLAN's `list[Message]` type. M5 must pass the serialized dict form from the transcript (e.g., using `ContextBuilder._normalize_messages()` or `Transcript.to_api_messages()` if that method exists). Check what the correct serialization call is before writing the stop hook.
  - The 7-layer gating must be ordered exactly as specified: `is_subloop` first (prevents recursion), `extraction_in_progress` fourth (prevents concurrent runs). Reordering breaks the at-least-once guarantee.
  - The runner's inner `provider.call()` path creates no new `AgentLoop` — there is no subloop flag to set. M5's guard is purely the `_maybe_extract_memories` gating, not a flag on the runner itself.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M5.md`
