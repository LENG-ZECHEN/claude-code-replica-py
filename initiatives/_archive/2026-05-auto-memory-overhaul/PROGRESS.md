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

## M5 — done 2026-05-24

- commit: [auto-mem/M5] (see git log)
- tests: 750 → 768 (+18 new tests across `test_has_memory_writes_since.py` (7),
  `test_extract_memories_gating.py` (8), `test_extract_memories_e2e.py` (3))
- mypy: clean | ruff: clean
- files changed: `extraction_hooks.py` (new), `loop.py` (modified, 788 lines),
  `metrics.py` (modified), `cli.py` (modified), `openai_cli.py` (modified),
  `tests/test_has_memory_writes_since.py` (new),
  `tests/test_extract_memories_gating.py` (new),
  `tests/test_extract_memories_e2e.py` (new)
- exit gate: `AgentLoop.run()` and `run_stream()` call `_run_stop_hooks(result)`
  before every return AND `maybe_extract_memories` enforces 7-layer gating in order
  AND `hasMemoryWritesSince` returns True for writes after cursor, False otherwise
  AND cursor advances on success, does NOT advance on exception (at-least-once)
  AND `--extract-memories` flag on both CLIs (env SIMPLE_AGENT_EXTRACT_MEMORIES)
  AND `MetricsCollector` gains `extract_invocations` + `extract_writes` counters
  AND 18 new tests → PASS
- notes: `extraction_hooks.py` extracted from loop.py to keep loop.py ≤800 lines
  (788). Defensive `hasattr(project_memory, "_dir")` check ensures pre-existing
  tests with mock ProjectMemory objects don't break. Both CLIs resolve
  `SIMPLE_AGENT_EXTRACT_MEMORIES` env var when flag is absent.

## M6 — done 2026-05-24

- commit: [auto-mem/M6] (see git log)
- tests: 768 → 784 (+16 new tests across `test_provider_selector.py` (8),
  `test_memdir_scan.py` (2), `test_memdir_manifest_format.py` (3), `test_memdir_recent_tools.py` (3))
- mypy: clean | ruff: clean
- files changed: `provider.py`, `memdir.py` (new), `test_provider_selector.py`,
  `test_memdir_scan.py`, `test_memdir_manifest_format.py`, `test_memdir_recent_tools.py`
- exit gate: call_selector on Provider Protocol AND `MockProvider(selector_responses=[...])`
  returns scripted responses sequentially AND `OpenAIProvider(selector_model=...)` uses
  configurable model (default "gpt-4o-mini") with JSON mode + temperature=0 AND raises
  `SelectorError` on API failure / malformed JSON / schema mismatch AND `memdir.py` exports
  `scan_memory_files`, `format_memory_manifest`, `collect_recent_successful_tools`,
  `SELECT_MEMORIES_SYSTEM_PROMPT` → PASS
- notes: `SELECT_MEMORIES_SYSTEM_PROMPT` copied verbatim from findRelevantMemories.ts
  lines 18-24. `scan_memory_files` and `MemoryHeader` re-exported from `memory.py` (no
  duplication). `collect_recent_successful_tools` stops at USER messages with string
  content (real human turns), correlates ToolCall.id → ToolResult.tool_use_id, returns
  names where is_error is False (using `is False` to exclude missing results). No
  AgentLoop changes — pure infrastructure milestone.

## M7 — done 2026-05-24

- commit: [auto-mem/M7] (see git log)
- tests: 784 → 807 (+23 new tests across `test_sidequery_recall.py` (9),
  `test_memdir_surfacing.py` (9), `test_loop_memory_injection.py` (5))
- mypy: clean | ruff: clean
- files changed: `memdir.py`, `loop.py`, `context.py`, `models.py`,
  `recall_hooks.py` (new), `test_sidequery_recall.py`, `test_memdir_surfacing.py`,
  `test_loop_memory_injection.py`
- exit gate: find_relevant_memories 4-gate enforced (auto_memory_enabled / non-empty /
  multi-word / session_bytes<60KB) AND hallucinated filenames dropped AND Jaccard fallback
  on SelectorError AND read_memories_for_surfacing ≤200 lines + ≤4KB truncation + staleness
  header AND AgentLoop.run() and run_stream() inject ATTACHMENT_MEMORY before Provider.call()
  AND already_surfaced deduplication AND session_bytes accumulates → PASS
- notes: loop.py extraction to `recall_hooks.py` (mirrors M5 `extraction_hooks.py`
  pattern) kept loop.py at exactly 800 lines. Empty memory directory short-circuits before
  calling call_selector (handles non-conforming Provider stubs in pre-M6 tests). ATTACHMENT_MEMORY
  messages are USER-role; `_coalesce_same_role` in context.py handles adjacency. models.py
  gains `MessageType.ATTACHMENT_MEMORY` and `Message.attachment_memory()` factory.
