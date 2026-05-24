# HANDOFF — Next: M1 (memory-md-format-and-frontmatter)

> Updated by: Phase 1 bootstrap of `auto-memory-overhaul`
> Date: 2026-05-24
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `auto-memory-overhaul`
- **current milestone**: _(not started)_
- **next milestone**: `M1` — memory-md-format-and-frontmatter
- **all milestones (per PLAN)**: M1 [next], M2 [pending], M3 [pending], M4 [pending], M5 [pending], M6 [pending], M7 [pending]

## 2. Completed milestones

_(none yet — this initiative has not started)_

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `6aed9ec` — `git show 6aed9ec`
- **tests**: 710 passing (1 pre-existing failure in `test_null_tracer_zero_overhead`)
- **mypy**: clean (22 source files, no issues)
- **ruff**: clean
- **branch**: main
- **known failing checks**: `test_null_tracer_zero_overhead` — pre-existing before this initiative

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: _(none yet — first milestone has free hand within its scope)_
- **preserve**: _(none yet)_
- **compatibility requirements**: _(none yet)_

## 5. Next milestone guidance

For `M1` — memory-md-format-and-frontmatter:

- **next scope**: Pure data-layer change. Transform `ProjectMemory.save()` to write `.md` files with YAML frontmatter (name, type, description, created_at). Add `scan_memory_files(dir)` that recursively returns `MemoryHeader[]` ordered by mtime. Rewrite `_update_manifest` to produce `MEMORY.md` with `- [name](rel/path.md) — description` lines, truncated at 200 lines OR 25KB. Add `simple-agent memory migrate-format` CLI subcommand. Keep `ProjectMemory.all()` reading both `.md` and legacy `.json` during the compat window.
- **relevant files**: `src/simple_coding_agent/memory.py` (heavy rewrite), `src/simple_coding_agent/memory_cli.py` (add migrate-format subcommand), `tests/test_memory.py` (rewrite expectations for .md), plus new test files: `tests/test_memory_frontmatter.py`, `tests/test_memory_manifest_format.py`, `tests/test_memory_scan_recursive.py`, `tests/test_memory_migrate.py`.
- **expected tests**: ≥10 new tests across the 4 new test files. Key coverage: frontmatter parsing (happy path, torn frontmatter, missing keys, >30-line frontmatter), manifest truncation (200-line limit, 25KB limit, warning footer), recursive scan (subdir entries, mtime ordering, MEMORY.md excluded), migrate-format CLI (idempotent, JSON→md, backward-compat dual-read).
- **risks**: The mini YAML parser is hand-rolled — frontmatter parse failures MUST yield `MemoryHeader(description=None)`, never raise. The manifest truncation logic is subtle: 25KB limit applies to the whole file, not per-entry. Subdir support in `_SAFE_ENTRY_ID_PATTERN` requires allowing `/`-separated segments while enforcing `Path.is_relative_to(root)` for traversal defense. Atomic write via `tempfile + os.replace` (see `transcript._atomic_write_json` for the pattern). TS reference: `claude-code-source-code/src/memdir/memdir.ts` + `memoryScan.ts`.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M1.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
