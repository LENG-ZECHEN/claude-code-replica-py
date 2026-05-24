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
