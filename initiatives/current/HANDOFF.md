# HANDOFF — Next: M4 (extract-memories-runner)

> Updated by: M3 execution (auto-mem/M3 session)
> Date: 2026-05-24
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `auto-memory-overhaul`
- **current milestone**: just-completed `M3` — memory-system-prompt-wiring
- **next milestone**: `M4` — extract-memories-runner
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [next], M5 [pending], M6 [pending], M7 [pending]

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
- **behavior implemented**: `ContextBuilder.__init__` gains `project_memory: ProjectMemory | None = None`. `_MEMORY_MANAGEMENT_SECTION` is a module-level string constant (~250 tokens, fully static). `ContextBuilder._build_system_prompt()` inserts this section between the CLAUDE.md/base section and the `## Memory` snippets block when `project_memory is not None`. `cli.py`'s `_build_repl_loop` now passes `project_memory=project_memory` to `ContextBuilder`. `openai_cli.py` needed no change — it routes through `_cli._build_repl_loop`. CLI single-instance sharing was already in place from M2 (both CLIs call `_open_project_memory` once and pass the result to both `AgentLoop` and `/remember` via `loop._project_memory`).
- **design decisions (deviations from PLAN)**:
  - **`openai_cli.py` unchanged**: PLAN listed it as a file to touch, but it already routes everything through `_cli._build_repl_loop`. The fix in `_build_repl_loop` propagates automatically. No separate change needed.
- **known limitations**:
  - (none)

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `[auto-mem/M3]` — `git -C python-replica log --oneline -1`
- **tests**: 739 passing (was 734 after M2, delta +5)
- **mypy**: clean (22 source files, no issues)
- **ruff**: clean
- **branch**: main
- **known failing checks**: `test_null_tracer_zero_overhead` — pre-existing before this initiative, not a regression

## 4. Important constraints (carried forward)

- **dual-read compat window**: `ProjectMemory.all()` and `load()` MUST continue reading legacy `.json` files until the migrate-format pass is run. Do not remove the `.json` fallback path until an explicit retirement milestone.
- **no PyYAML dependency**: frontmatter parsing stays hand-rolled (`_parse_frontmatter`); fail-soft (broken frontmatter yields `MemoryHeader(description=None)`, never raises).
- **atomic manifest writes**: `_update_manifest` uses `tempfile.mkstemp` + `os.replace`. Do not revert to direct open/write.
- **path traversal defense**: `_SAFE_ENTRY_ID_PATTERN` allows `/` for subdir IDs but excludes `.` — `Path.is_relative_to(root)` is the second gate. Both layers must be preserved in M4+.
- **secret rejection**: `_check_body_for_secrets` in `ProjectMemory.save()` must remain active and surface as `ValueError` for all callers (CLI exit code 2, tool `is_error=True`).
- **quota counter reset**: `AgentLoop._memory_writes_this_turn` is reset to `0` at the start of each `run()` / `run_stream()`. M4+ must not remove or bypass this reset.
- **conditional tool registration**: `write_memory_entry` is registered in `AgentLoop._register_tools()` ONLY when `self._project_memory is not None`. M4 must pass a `ProjectMemory` instance to `AgentLoop.__init__` for the tool to be active.
- **`_MEMORY_MANAGEMENT_SECTION` is a frozen constant**: M4's `ExtractMemoriesRunner` must NOT modify or shadow this constant; the section's byte-identical content is required for prompt-cache stability. Any changes to the teaching text require a separate milestone.
- **M4's `ExtractMemoriesRunner` must receive a snapshot of `base_messages`**: It must NOT hold a live reference to the main transcript. The caller passes a snapshot at construction time so the runner's inner loop cannot mutate live history.

## 5. Next milestone guidance

For `M4` — extract-memories-runner:

- **next scope**: Create `src/simple_coding_agent/extract_memories.py` with the pure `ExtractMemoriesRunner` class and `ExtractionResult` dataclass. The runner takes `(provider, memory_dir, system_prompt, base_messages, tool_registry)`, runs a 5-turn inner loop with a tool whitelist `{read_file, list_files, search_text, write_memory_entry}`, and returns `ExtractionResult{written_paths, errors, turn_count}`. It has NO coupling to `AgentLoop` — M5 wires the stop-hook integration. `build_extract_prompt(new_message_count, existing_memories_manifest)` is a free function that builds the 5-section extraction prompt.
- **relevant files**:
  - `src/simple_coding_agent/extract_memories.py` — new file; the entire M4 scope lives here
  - `src/simple_coding_agent/coding_tools.py` — reference for `write_memory_entry` schema + function signature (the runner's tool whitelist wraps it)
  - `src/simple_coding_agent/loop.py` — read for the `_register_tools` pattern; do NOT modify in M4
  - `src/simple_coding_agent/memory.py` — reference for `ProjectMemory` storage path; the runner writes to `memory_dir` via the tool
  - `tests/test_extract_memories_runner.py` — new; 8+ tests with MockProvider scripted sequences
- **expected tests** (≥8 per PLAN):
  - Happy path: MockProvider scripts a `write_memory_entry` tool_use → `ExtractionResult.written_paths` contains the path
  - MAX_TURNS cap: model keeps issuing tool_use at turn 5 → `errors=["max turns reached"]`, no exception raised
  - Tool whitelist enforcement: model attempts a tool not in the whitelist → `tool_result.is_error=True`
  - `build_extract_prompt` produces the 5-section prompt with correct `new_message_count` and manifest
  - Multi-turn sequence: model reads a file then writes a memory → both tool calls succeed, one written path
  - `write_memory_entry` path traversal blocked (existing `_SAFE_ENTRY_ID_PATTERN` in `ProjectMemory.save`)
  - Empty base_messages: runner still runs without crashing
  - Model returns stop on turn 1: `turn_count=1`, `written_paths=[]`, `errors=[]`
- **risks**:
  - The PLAN specifies the whitelist is enforced by a wrapper around `tool_registry.execute()` that inspects tool name. Be careful that the wrapper correctly threads `write_memory_entry`'s `project_memory` dependency — the runner should construct its own `ProjectMemory(memory_dir)` instance and pass it to a local `write_memory_entry` wrapper, NOT reuse the main agent's registry.
  - `ExtractionResult.written_paths` should contain resolved `.md` file paths (matching what `ProjectMemory.save()` writes), so M5 can display them in a summary message.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M4.md`
