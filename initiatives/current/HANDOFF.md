# HANDOFF — Next: M3 (memory-system-prompt-wiring)

> Updated by: M2 execution (auto-mem/M2 session)
> Date: 2026-05-24
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `auto-memory-overhaul`
- **current milestone**: just-completed `M2` — write-memory-entry-tool
- **next milestone**: `M3` — memory-system-prompt-wiring
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [next], M4 [pending], M5 [pending], M6 [pending], M7 [pending]

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

## 3. Current repo state

> Re-verify these numbers before starting. Do not trust this list blindly.

- **last commit**: `[auto-mem/M2]` — `git -C python-replica log --oneline -1`
- **tests**: 734 passing (was 724 after M1, delta +10)
- **mypy**: clean (22 source files, no issues)
- **ruff**: clean
- **branch**: main
- **known failing checks**: `test_null_tracer_zero_overhead` — pre-existing before this initiative, not a regression

## 4. Important constraints (carried forward)

- **dual-read compat window**: `ProjectMemory.all()` and `load()` MUST continue reading legacy `.json` files until the migrate-format pass is run. Do not remove the `.json` fallback path until an explicit retirement milestone.
- **no PyYAML dependency**: frontmatter parsing stays hand-rolled (`_parse_frontmatter`); fail-soft (broken frontmatter yields `MemoryHeader(description=None)`, never raises).
- **atomic manifest writes**: `_update_manifest` uses `tempfile.mkstemp` + `os.replace`. Do not revert to direct open/write.
- **path traversal defense**: `_SAFE_ENTRY_ID_PATTERN` allows `/` for subdir IDs but excludes `.` — `Path.is_relative_to(root)` is the second gate. Both layers must be preserved in M3+.
- **secret rejection**: `_check_body_for_secrets` in `ProjectMemory.save()` must remain active and surface as `ValueError` for all callers (CLI exit code 2, tool `is_error=True`).
- **quota counter reset**: `AgentLoop._memory_writes_this_turn` is reset to `0` at the start of each `run()` / `run_stream()`. M3+ must not remove or bypass this reset.
- **conditional tool registration**: `write_memory_entry` is registered in `AgentLoop._register_tools()` ONLY when `self._project_memory is not None`. M3 must pass a `ProjectMemory` instance to `AgentLoop.__init__` for the tool to be active.

## 5. Next milestone guidance

For `M3` — memory-system-prompt-wiring:

- **next scope**: Add a `## Memory Management` teaching section (~250-token, static, cache-friendly) to `ContextBuilder._build_system_prompt()`, inserted between the CLAUDE.md section and the `## Memory` snippets block. The section explains the 4 memory types, what to save, what NOT to save, and mentions that `write_memory_entry` is available. Wire CLI entrypoints (`cli.py`, `openai_cli.py`) to construct a single `ProjectMemory` instance shared between `AgentLoop.__init__` and the existing `/remember` REPL handler. Add an end-to-end test proving that a model-emitted `write_memory_entry` tool_use lands a `.md` file with correct frontmatter via `MockProvider`.
- **relevant files**:
  - `src/simple_coding_agent/context.py` — add `## Memory Management` section in `_build_system_prompt()`; takes `project_memory: ProjectMemory | None` kwarg
  - `src/simple_coding_agent/cli.py` — construct `ProjectMemory` once, pass to both `AgentLoop` and the `/remember` slash command handler
  - `src/simple_coding_agent/openai_cli.py` — same as cli.py
  - `src/simple_coding_agent/loop.py` — already wired (M2 done); no new changes expected
  - `tests/test_loop_memory_prompt.py` — verify teaching section appears in system prompt when project_memory is provided
  - `tests/test_loop_write_memory_e2e.py` — end-to-end: MockProvider emits write_memory_entry tool_use, file lands on disk
- **expected tests** (≥5 per PLAN):
  - `test_loop_memory_prompt.py` — system prompt includes `## Memory Management` when `project_memory` is provided; absent when not provided
  - `test_loop_write_memory_e2e.py` — full loop run: MockProvider scripts a `write_memory_entry` tool call, check that `.md` file appears in the memory dir
  - Additional test: `/remember` and `write_memory_entry` share the same `ProjectMemory` instance (write via one, read via the other)
- **risks**:
  - The teaching section insert position (after CLAUDE.md separator, before `## Memory` snippets) must not break the prompt cache prefix. The static text should come first; dynamic snippets after. Verify the insert order in `_build_system_prompt`.
  - M3 must pass the SAME `ProjectMemory` instance to both `AgentLoop.__init__` and the `/remember` REPL handler — not two separate instances pointing at the same directory (they would both work independently but the shared-instance test would fail if checked via `is`).

The full ready-to-run prompt is at:
`initiatives/current/prompts/M3.md`
