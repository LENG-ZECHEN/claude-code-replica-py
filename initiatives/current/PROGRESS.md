# auto-memory-overhaul progress log

Cumulative milestone log for the `auto-memory-overhaul` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[auto-mem/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

## M1 — done 2026-05-24

- **commit**: `612487d`
- **tests**: 724 passing (711 baseline + 13 new); +13 new tests across 4 new files
- **mypy**: clean
- **ruff**: clean
- **what shipped**:
  - `ProjectMemory.save()` writes `<id>.md` with YAML frontmatter (name, type, description, created_at)
  - Hand-rolled `_parse_frontmatter` (fail-soft, no PyYAML, 30-line limit)
  - `MemoryHeader` frozen dataclass + `scan_memory_files()` (recursive glob, mtime-desc, excludes MEMORY.md)
  - `MEMORY.md` manifest with 200-line + 25KB truncation, atomic write via tempfile+os.replace
  - Dual-read compat: `all()` reads `.md` + legacy `.json`; `load()` tries `.md` first
  - `migrate-format` CLI subcommand (idempotent JSON→MD)
  - `_SAFE_ENTRY_ID_PATTERN` extended to allow `/` for subdir IDs (`.` excluded, `..` blocked)
  - New test files: `test_memory_frontmatter.py` (4), `test_memory_manifest_format.py` (4), `test_memory_scan_recursive.py` (3), `test_memory_migrate.py` (2)

## M2 — done 2026-05-24

- commit: [auto-mem/M2] (see git log)
- tests: 724 → 734 (+10 new tests in `test_write_memory_tool.py`)
- mypy: clean | ruff: clean
- files changed: `coding_tools.py`, `loop.py`, `tests/test_write_memory_tool.py`
- exit gate: write_memory_entry exported + 10 schema/quota/upsert/registration tests pass → PASS
- notes: `project_memory` kwarg on AgentLoop was already present from P9-M5; only added
  `_memory_writes_this_turn` counter, `_register_tools()` method, and reset in run()/run_stream().
  Registration function is inline closure inside `_register_tools` (captures `self`) rather than
  a standalone exported function — this gives the closure direct access to `self._memory_writes_this_turn`
  for resetting without a separate mutable container.

## M3 — done 2026-05-24

- commit: [auto-mem/M3] (see git log)
- tests: 734 → 739 (+5 new tests in `test_loop_memory_prompt.py`, `test_loop_write_memory_e2e.py`)
- mypy: clean | ruff: clean
- files changed: `context.py`, `cli.py`,
  `tests/test_loop_memory_prompt.py`, `tests/test_loop_write_memory_e2e.py`
- exit gate: system prompt has ## Memory Management when project_memory provided AND
  e2e write_memory_entry tool_use lands .md file on disk → PASS
- notes: `openai_cli.py` required no change — it already routes through
  `_cli._build_repl_loop` which now passes `project_memory` to `ContextBuilder`.
  Single shared instance was already in place from M2 (both CLIs call
  `_open_project_memory` once and pass to `AgentLoop`). CLI sharing already
  wired; M3 only added the static teaching section and ContextBuilder threading.

## M4 — done 2026-05-24

- commit: [auto-mem/M4] (see git log)
- tests: 739 → 750 (+11 new tests in `test_extract_memories_runner.py`)
- mypy: clean | ruff: clean
- files changed: `extract_memories.py` (new), `tests/test_extract_memories_runner.py` (new)
- exit gate: ExtractMemoriesRunner.run() returns ExtractionResult AND MAX_TURNS=5
  AND whitelist enforced → PASS (11 new tests)
- notes: `base_messages` is stored as a snapshot copy at construction time but is NOT
  injected into the inner message loop in M4 (M5 will determine what context to pass).
  Tool whitelist enforced via `_execute_tool` dispatcher: non-whitelisted tools return
  is_error=True without touching the registry; `write_memory_entry` creates a local
  `ProjectMemory(memory_dir)` instance (path traversal defense from M1 still active).
  `_build_whitelist_tools()` iterates sorted whitelist, pulling specs from registry for
  read_file/list_files/search_text and using hardcoded schema for write_memory_entry
  (since the registry may have it bound to a different ProjectMemory). The for/else
  pattern cleanly handles the MAX_TURNS=5 cap without a separate sentinel flag.
