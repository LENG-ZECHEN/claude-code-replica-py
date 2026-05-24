# HANDOFF — Next: M2 (write-memory-entry-tool)

> Updated by: M1 execution (auto-mem/M1 session)
> Date: 2026-05-24

---

## 1. Current initiative

- **slug**: `auto-memory-overhaul`
- **current milestone**: M1 — memory-md-format-and-frontmatter ✓ done
- **next milestone**: `M2` — write-memory-entry-tool
- **all milestones (per PLAN)**: M1 [done], M2 [next], M3 [pending], M4 [pending], M5 [pending], M6 [pending], M7 [pending]

## 2. Completed milestones

- **M1** (`612487d`, 2026-05-24) — `.md` frontmatter format, `scan_memory_files`, `migrate-format` CLI.
  - `ProjectMemory.save()` now writes `<id>.md` with YAML frontmatter.
  - `scan_memory_files(dir)` recursively returns `MemoryHeader[]` ordered by mtime desc.
  - `MEMORY.md` manifest: `- [name](rel/path.md) — description` lines, truncated at 200 lines OR 25KB.
  - `simple-agent memory migrate-format` converts `.json` → `.md` idempotently.
  - Dual-read compat window: `all()` + `load()` read both `.md` and legacy `.json`.
  - 13 new tests; pytest 711 → 724; mypy + ruff clean.

## 3. Current repo state

- **last commit**: `612487d` — `[auto-mem/M1] .md frontmatter format, scan, migrate-format CLI`
- **tests**: 724 passing
- **mypy**: clean (22 source files, no issues)
- **ruff**: clean
- **branch**: main
- **known failing checks**: `test_null_tracer_zero_overhead` — pre-existing before this initiative, not a regression

## 4. Important constraints (carried forward)

- **dual-read compat window**: `ProjectMemory.all()` and `load()` MUST continue reading legacy `.json` files until the migrate-format pass is run. Do not remove the `.json` fallback path until an explicit retirement milestone.
- **no PyYAML dependency**: frontmatter parsing stays hand-rolled (`_parse_frontmatter`); fail-soft (broken frontmatter yields `MemoryHeader(description=None)`, never raises).
- **atomic manifest writes**: `_update_manifest` uses `tempfile.mkstemp` + `os.replace`. Do not revert to direct open/write.
- **path traversal defense**: `_SAFE_ENTRY_ID_PATTERN` allows `/` for subdir IDs but excludes `.` — `Path.is_relative_to(root)` is the second gate. Both layers must be preserved in M2+.
- **secret rejection**: `_check_body_for_secrets` in `ProjectMemory.save()` must remain active and surface as `ValueError` for all callers (CLI exit code 2, tool is_error=True in M2).

## 5. Next milestone guidance

For `M2` — write-memory-entry-tool:

- **scope**: Tool layer only — does NOT add the teaching prompt (that is M3). Add `coding_tools.write_memory_entry(type, id, name, description, body, tags)` exported via `__all__`. Validate type ∈ {user, feedback, project, reference}, id against safe pattern, description ≤ 150 chars, body not matching secret patterns. Upsert on same id. Add `AgentLoop._memory_writes_this_turn` counter that blocks the 4th write/turn with `"memory write quota exhausted this turn (max 3)"` as `tool_result` with `is_error=True`. Register the tool in `AgentLoop` only when `project_memory` is provided.
- **relevant files**: `src/simple_coding_agent/coding_tools.py` (new tool function + schema), `src/simple_coding_agent/loop.py` (counter + conditional registration in `_register_tools`), `tests/test_write_memory_tool.py` (new, ≥7 tests).
- **registration pattern**: mirror `snip_tool_model.register_snip_history_tool` — write `register_write_memory_entry_tool(registry, project_memory)`. The tool only exists when `project_memory` is provided. `AgentLoop.__init__` gains an optional `project_memory: ProjectMemory | None` keyword arg (default `None` for backward compat).
- **quota reset**: `_memory_writes_this_turn` resets to 0 at the start of each `run()` / `run_stream()` call.
- **expected tests** (≥7): schema validation (unknown type, bad id, long description, secret body), quota (3rd write succeeds, 4th is error), upsert (same id overwrites body), tool absent when `project_memory=None`.
- **exit gate** (per PLAN): tool exists + exported + validates type/id/description/body + blocks 4th write + registered only when ProjectMemory provided + pytest green with ≥7 new tests.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M2.md`
