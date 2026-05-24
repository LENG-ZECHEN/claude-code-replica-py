---
slug: auto-memory-overhaul
commit_prefix: auto-mem

milestones:
  #
  # 7 milestones; each is single-concern to stay under the SIZING GUIDANCE
  # water marks. The original analysis report (≈ 470 lines, see Anything else)
  # grouped this work into 3 big phases (M-α′ / M-γ / M-β) of ~3 days each;
  # M-α′ alone hits ≥3 of the 4 split triggers (touches 6 files + introduces
  # frontmatter abstraction + wires loop + exposes migrate CLI + ~11 new tests),
  # so it is pre-split into M1 / M2 / M3 by data-layer / tool-layer / wiring-layer.
  # M-γ and M-β are likewise pre-split. M-ε (threading-based async sideQuery)
  # is intentionally deferred to a follow-up initiative.
  #
  # Execution order is strictly M1 → M2 → M3 → M4 → M5 → M6 → M7.
  # M6 could technically run earlier (no hard dependency on M5), but the
  # linear order matches the prioritisation we agreed on:
  # "first writes (α′), then extract-fallback (γ), then optimised reads (β)."
  #
  M1:
    name: memory-md-format-and-frontmatter
    phase_ids: [A1]
    exit_gate: |
      `ProjectMemory.save(entry)` writes `<id>.md` with YAML frontmatter
      (name, type, description, created_at) AND `scan_memory_files(dir)`
      recursively returns `MemoryHeader[]` ordered by mtime AND `MEMORY.md`
      is regenerated with `- [name](rel/path.md) — description` lines,
      truncated at 200 lines OR 25KB with a warning footer AND
      `simple-agent memory migrate-format` converts existing `.json` to `.md`
      idempotently AND `ProjectMemory.all()` reads both `.md` and legacy `.json`
      during the compat window AND `pytest --tb=no -q` is green with at least
      10 new tests covering frontmatter parsing, manifest truncation, recursive
      scan, and migrate-format CLI.
    notes: |
      Pure data-layer change; no tool/loop wiring.
      Files: src/simple_coding_agent/memory.py (heavy), memory_cli.py
      (add migrate-format subcommand), tests/test_memory_frontmatter.py,
      test_memory_manifest_format.py, test_memory_scan_recursive.py,
      test_memory_migrate.py (new); existing test_memory.py expectations
      rewritten for .md format.
      Mini YAML parser is hand-rolled (no PyYAML dep) — only 4-5 keys,
      fail-soft (broken frontmatter → MemoryHeader with description=None,
      filename still usable).
      Subdir support: extend _SAFE_ENTRY_ID_PATTERN to allow `/`-separated
      segments, use Path.is_relative_to(root) for traversal defense.
      Manifest excludes MEMORY.md itself (basename check).
      Atomic write: switch _update_manifest to tempfile + os.replace —
      mirror the pattern already used by `transcript._atomic_write_json`
      and `session_store` (see CLAUDE.md M4 section).
      TS reference: claude-code-source-code/src/memdir/memdir.ts +
      memoryScan.ts (see report § 2.1 in the companion plan file).

  M2:
    name: write-memory-entry-tool
    phase_ids: [B1]
    exit_gate: |
      `coding_tools.write_memory_entry(type, id, name, description, body, tags)`
      exists and is exported via `__all__` AND validates type ∈
      {user, feedback, project, reference} AND validates id against the safe
      pattern AND rejects description > 150 chars AND rejects body matching
      secret patterns AND upserts on same id AND
      `AgentLoop._memory_writes_this_turn` counter blocks the 4th write/turn
      with `"memory write quota exhausted this turn (max 3)"` returned as
      tool_result is_error=True AND tool is registered in AgentLoop only when
      ProjectMemory is provided AND `pytest --tb=no -q` is green with at least
      7 new tests covering schema validation, quota, and upsert semantics.
    notes: |
      Tool layer only — does NOT add the teaching prompt yet (that is M3).
      Files: src/simple_coding_agent/coding_tools.py (new tool function +
      schema), loop.py (counter + conditional registration in _register_tools),
      tests/test_write_memory_tool.py (new).
      TOOL REGISTRATION PATTERN: mirror snip_tool_model.register_snip_history_tool
      (snip_tool_model.py) — that function takes (registry, captured_runtime_state)
      and returns the registered Tool. Write `register_write_memory_entry_tool(
      registry, project_memory)` so the tool only exists when project_memory
      is provided. This keeps M2 schema-symmetric with the model-driven snip
      tool that ctx-mgmt-pdf-align M4 already shipped.
      Tool wraps ProjectMemory.save() — reuses M1's frontmatter serialization,
      secret rejection, path traversal defense. Same `_check_body_for_secrets`
      and `_SAFE_ENTRY_ID_PATTERN` defenses from M1.
      AgentLoop.__init__ gains an optional `project_memory: ProjectMemory | None`
      keyword arg (defaults None for backward compat).
      Quota state lives on the loop instance as `_memory_writes_this_turn: int`,
      reset to 0 at the start of each run() / run_stream() call (see explicit
      test in test_write_memory_tool.py).

  M3:
    name: memory-system-prompt-wiring
    phase_ids: [B2]
    exit_gate: |
      `ContextBuilder._build_system_prompt()` inserts a `## Memory Management`
      teaching section before `## Memory` when project_memory is provided AND
      the section explains 4 types, what to save, what NOT to save, and points
      to the existing index AND CLI entrypoints (`simple-agent`,
      `simple-agent-openai`) construct ProjectMemory once and pass to both
      AgentLoop and the existing `/remember` REPL handler (single instance
      shared) AND a MockProvider e2e test proves a model-emitted
      `write_memory_entry` tool_use lands a `.md` file with correct frontmatter
      AND `pytest --tb=no -q` is green with at least 5 new tests.
    notes: |
      Wiring milestone — depends on M1 (frontmatter format) and M2 (tool exists).
      Files: src/simple_coding_agent/context.py (prompt section in
      _build_system_prompt), cli.py + openai_cli.py (share ProjectMemory
      instance with REPL /remember handler), tests/test_loop_memory_prompt.py +
      test_loop_write_memory_e2e.py (new).
      The teaching prompt text is English, ~250 tokens, fully static
      (cache-friendly). Insert position: between CLAUDE.md section
      (already prepended via "\n\n---\n\n" separator per P6) and the existing
      `## Memory` snippets block, so the static teaching is upstream of
      dynamic snippets and preserves the cache prefix.
      No changes to existing /remember slash command — it MUST continue to
      work because the same ProjectMemory instance backs both write paths
      (verified by an explicit test: /remember writes entry X, model-emitted
      write_memory_entry overwrites X, MEMORY.md ends up with one entry).
      Teaching content draft: see § 15.4 of the companion plan file.

  M4:
    name: extract-memories-runner
    phase_ids: [C1]
    exit_gate: |
      `extract_memories.ExtractMemoriesRunner(provider, memory_dir,
      system_prompt, base_messages, tool_registry)` class exists AND
      `.run(new_message_count)` returns
      `ExtractionResult{written_paths, errors, turn_count}` AND the inner
      loop respects MAX_TURNS=5 AND the tool whitelist is enforced: only
      {read_file, list_files, search_text, write_memory_entry} are accepted;
      other tool names yield a tool_result with is_error=True AND the
      5-section extraction prompt (opener / immediate action / types /
      what-not-to-save / how-to-save) is built by `build_extract_prompt(
      new_message_count, existing_memories_manifest)` AND
      `pytest --tb=no -q` is green with at least 8 new tests using MockProvider
      scripted tool_use sequences.
    notes: |
      Pure engine; no stop-hook integration (that is M5).
      Files: src/simple_coding_agent/extract_memories.py (new),
      tests/test_extract_memories_runner.py (new).
      The runner does NOT touch the main AgentLoop; it consumes a snapshot
      of base_messages and returns ExtractionResult. The caller (M5) is
      responsible for cursor advancement and integration with the loop.
      Tool whitelist is enforced by a wrapper around tool_registry.execute()
      that inspects tool name and (for write_memory_entry) verifies the
      file_path resolves into memory_dir — reuses existing tool implementations
      rather than creating a separate registry.
      5 turns is the hard cap; if the model still has tool_use at turn 5,
      the runner closes with `errors=["max turns reached"]` (does NOT raise).
      Returns ExtractionResult.written_paths so M5 can append a summary
      `SystemMessage("Saved N memories: ...")` into the parent transcript.

  M5:
    name: extract-stop-hook-and-gating
    phase_ids: [C2]
    exit_gate: |
      `AgentLoop.run()` and `run_stream()` both call
      `_run_stop_hooks(result)` before returning AND
      `_maybe_extract_memories()` enforces 7-layer gating in order:
      (1) is_subloop, (2) extract_memories_enabled flag, (3) auto_memory_enabled,
      (4) extraction_in_progress, (5) hasMemoryWritesSince, (6) throttle
      counter, (7) run AND `hasMemoryWritesSince(messages, since_uuid)`
      returns True when any assistant message after the cursor calls
      write_memory_entry AND the cursor `_last_memory_message_uuid` advances
      on success AND does NOT advance on exception (at-least-once retry) AND
      `--extract-memories` flag is exposed on both CLIs (default off,
      resolvable via env SIMPLE_AGENT_EXTRACT_MEMORIES through
      cli._resolve_threshold-style precedence) AND `MetricsCollector` gains
      `extract_invocations` and `extract_writes` counters incremented at the
      runner's success site AND `pytest --tb=no -q` is green with at least
      9 new tests covering each gating layer, cursor logic, and metrics.
    notes: |
      Wiring milestone — depends on M2 (write_memory_entry tool exists so
      hasMemoryWritesSince has something to detect) and M4 (Runner exists).
      Files: src/simple_coding_agent/loop.py (stop hook + gating + state
      fields _last_memory_message_uuid, _extraction_in_progress,
      _turns_since_last_extraction), metrics.py (2 new counters), cli.py +
      openai_cli.py (flag), tests/test_extract_memories_gating.py +
      test_has_memory_writes_since.py + test_extract_memories_e2e.py (new).
      FLAG PRECEDENCE: follow the cli._resolve_threshold(explicit > preset >
      default) pattern already used by --max-context-tokens, --max-steps,
      --output-headroom etc. (see CLAUDE.md observable-thresholds-harden M2).
      The new --extract-memories flag is NOT part of --aggressive-thresholds
      (extraction has cost implications; user must opt in explicitly).
      Default `extract_memories_enabled=False`. Throttle default n=1 (every
      turn); raise via env SIMPLE_AGENT_EXTRACT_THROTTLE for cost control.
      METRICS: extend MetricsCollector with extract_invocations (counts every
      time _maybe_extract_memories actually invokes the runner, i.e. passes
      all 7 gates) and extract_writes (sum of len(written_paths) per run).
      Format /stats line: "extract_invocations=N extract_writes=M".
      The is_subloop guard is critical: ExtractMemoriesRunner internally
      MUST set its tool-execution path's runner context to _is_subloop=True
      so that even if the runner shells out via something that triggers
      a stop_hooks path, it short-circuits at layer (1).

  M6:
    name: provider-selector-and-memdir-infra
    phase_ids: [D1]
    exit_gate: |
      `Provider` Protocol gains `call_selector(*, system, user, output_schema,
      max_tokens=256) -> dict` AND `MockProvider(selector_responses=[...])`
      returns scripted responses round-robin AND
      `OpenAIProvider(selector_model=...)` uses a configurable cheaper model
      (default "gpt-4o-mini") with JSON mode and temperature=0 AND raises
      `SelectorError` on API failure / malformed JSON / schema mismatch AND
      a new module `src/simple_coding_agent/memdir.py` exports
      `scan_memory_files`, `format_memory_manifest`,
      `collect_recent_successful_tools`, and the verbatim
      `SELECT_MEMORIES_SYSTEM_PROMPT` constant AND
      `pytest --tb=no -q` is green with at least 10 new tests.
    notes: |
      Infrastructure milestone; no AgentLoop touch yet (that is M7).
      Files: src/simple_coding_agent/provider.py (Protocol method + Mock +
      OpenAI impls), memdir.py (new), tests/test_provider_selector.py +
      test_memdir_scan.py + test_memdir_manifest_format.py +
      test_memdir_recent_tools.py (new).
      SELECT_MEMORIES_SYSTEM_PROMPT is copied VERBATIM from
      claude-code-source-code/src/memdir/findRelevantMemories.ts lines 18-24;
      do NOT paraphrase — the "if a list of recently-used tools is provided"
      clause and the "warnings, gotchas, or known issues" carve-out are
      both load-bearing.
      scan_memory_files reads only the first 30 lines per file
      (FRONTMATTER_MAX_LINES = 30) to build MemoryHeader cheaply.
      collect_recent_successful_tools reverse-scans the transcript from end
      until the previous human turn; correlates tool_use.id to
      tool_result.tool_use_id to filter out errored calls (mirrors the
      existing pairing logic in snip.py).
      OpenAIProvider gains __init__ kwarg `selector_model: str = "gpt-4o-mini"`
      so DashScope / qwen3.6-plus / other endpoints can swap in their own
      cheap model.

  M7:
    name: sidequery-recall-and-injection
    phase_ids: [D2]
    exit_gate: |
      `memdir.find_relevant_memories(query, dir, selector, *, already_surfaced,
      read_file_state, recent_tools, session_bytes_used)` enforces 4 gates
      (auto_memory_enabled, non-empty query, multi-word query,
      session_bytes_used < 60KB) AND validates returned filenames against the
      scan manifest AND `memdir.read_memories_for_surfacing(selected)` reads
      ≤200 lines + ≤4KB per file with a truncation warning AND builds a
      staleness-aware header ("Memory (saved 3 days ago): ...") AND
      `AgentLoop.run()` AND `run_stream()` call find + read_memories
      synchronously before Provider.call() AND inject results as
      `<system-reminder>`-wrapped ATTACHMENT messages into the transcript AND
      selector failure falls back to the existing Jaccard MemorySelector AND
      `pytest --tb=no -q` is green with at least 9 new tests covering gates,
      validation, truncation, fallback, and end-to-end injection.
    notes: |
      Wiring milestone — depends on M1 (.md format), M6 (Provider.call_selector
      + memdir infra).
      Files: src/simple_coding_agent/memdir.py (extend), loop.py (sideQuery
      call + attachment injection in run() and run_stream()), context.py
      (recognize the new ATTACHMENT_MEMORY sub-type, serialize to API
      messages without breaking _coalesce_same_role — see CLAUDE.md
      ctx-mgmt-pdf-align post-review follow-up),
      tests/test_sidequery_recall.py + test_memdir_surfacing.py +
      test_loop_memory_injection.py (new).
      SYNCHRONOUS FORM ONLY: sideQuery runs to completion BEFORE
      Provider.call() in each turn. Threading async form (M-ε in the original
      report § 5.2.2) is deferred to a follow-up initiative.
      Session bytes accumulator lives on the AgentLoop instance, persists
      across turns within a single CLI session (resets on new loop).
      already_surfaced set deduplicates within session; read_file_state set
      deduplicates against files the main agent has already Read.
      Tracer integration: emit on the existing `memory_select` channel with
      keys {selected_count, manifest_size, session_bytes_used, fallback_used}.
      Selector failure path emits `memory_select` with fallback_used=True and
      the loop continues with Jaccard results — never raises out of the loop.
---

> Bootstrapped on 2026-05-24. Baseline commit: `6aed9ec`. Baseline pytest: 710 passing (1 pre-existing failure in `test_null_tracer_zero_overhead` — pre-initiative). Baseline mypy/ruff: clean. Sizing assessment: all 7 milestones are single-concern pre-splits; the largest (M1) touches 3 src files + ~10 new tests and does NOT combine abstraction+wire+CLI. SIZING WAIVED: none.

# Goal

Bring the Python replica's memory module from "user-driven write, Jaccard
sync read" up to the source-code form: `.md` files with YAML frontmatter,
an index file that the model itself maintains, sideQuery LLM recall, and
an ExtractMemories subloop that auto-captures what the main agent forgot
to save.

After this initiative completes, all four memory-write paths from the
source-code design exist and work end-to-end in the replica:

- CLI `simple-agent memory add` (already existed)
- REPL `/remember <type> <id> <body>` (already existed)
- Main agent calling `write_memory_entry` tool during conversation (M2 + M3)
- ExtractMemories subloop after each turn that didn't write (M4 + M5)

And the read path upgrades from Jaccard to LLM-based sideQuery (M6 + M7),
with Jaccard kept as a fallback when the selector errors out.

# Background / motivation

The replica's current `ProjectMemory` writes `<id>.json` per entry with a
flat `# Memory Index` heading and no frontmatter. Source-code Claude
maintains `.md` files with YAML frontmatter, organizes them in
subdirectories, and uses a separate Sonnet call to pick the ≤5 most
relevant memories per turn. The replica also has zero auto-extraction —
it only triggers a regex cue ("记住" / "don't" / "prefer", via
`auto_learn.detect_cue`) and prints a hint asking the user to run
`/remember` manually.

The full gap analysis (≈ 470 lines of source-aligned design notes, fact
verification, and per-section change recipes) lives in
`~/.claude/plans/auto-memory-gentle-catmull.md`. Section references in
each milestone's `notes` block point back to that document for the
verbatim source quotations, prompt templates, and risk catalogue.

This initiative does NOT close the gap to the ts source completely —
M-ε (threading-based async sideQuery) and several smaller items in the
"Out of scope" list below are intentionally deferred. The goal is the
single-process synchronous path that exercises every mechanism's main
behaviour end-to-end.

# Design sketch

Seven milestones in three thematic groups. Dependency DAG:

```
M1 (data) ──┬─→ M2 (tool) ──→ M3 (wiring) ──→ M4 (engine) ──→ M5 (extraction)
            │                                                       │
            └───────────────→ M6 (infra) ────→ M7 (recall) ←────────┘
                                              (also depends on M1)
```

Execution order is strictly M1 → M2 → M3 → M4 → M5 → M6 → M7. The DAG
allows M6 to run after M1 (it doesn't need M5), but the linear order
matches the "first writes (α′), then extract-fallback (γ), then optimised
reads (β)" priority confirmed during planning.

**M1 (data layer)**: `.md` + frontmatter + recursive scan + 200/25KB
manifest truncation + migrate-format CLI. Foundation for everything
else. Hand-rolled mini YAML parser, no new dependency. Subdir support
via segment-validated paths + traversal defense.

**M2 (tool layer)**: `write_memory_entry(type, id, name, description,
body, tags)` tool with schema validation, secret rejection, upsert
semantics, and a per-turn quota of 3. Mirrors the
`register_snip_history_tool` registration pattern. Wraps
`ProjectMemory.save()` so all M1 defenses apply.

**M3 (prompt wiring)**: Add a ~250-token English `## Memory Management`
teaching section to the system prompt between the CLAUDE.md section and
the dynamic `## Memory` snippets (cache-prefix stable), plus share a
single `ProjectMemory` instance between the existing `/remember` REPL
handler and the new tool path.

**M4 (extraction engine)**: `ExtractMemoriesRunner` as a pure class —
takes provider + base messages + tool registry, runs a 5-turn inner
loop with the whitelist {read_file, list_files, search_text,
write_memory_entry}, returns `ExtractionResult`. Builds the 5-section
extraction prompt (opener / immediate action / types / what-not-to-save
/ how-to-save) as a template function.

**M5 (extraction wiring)**: Stop hook in `AgentLoop.run()` and
`run_stream()` calls `_maybe_extract_memories` after every turn.
7-layer gating: is_subloop / flag / auto_memory_enabled / in_progress /
hasMemoryWritesSince / throttle / run. `hasMemoryWritesSince` scans
assistant messages after the cursor for `write_memory_entry` tool_use.
At-least-once cursor (only advances on success). Default off,
throttle=1, opt-in via `--extract-memories` (precedence resolved via
the existing `_resolve_threshold` pattern). MetricsCollector gains
`extract_invocations` / `extract_writes`.

**M6 (selector infrastructure)**: Add `Provider.call_selector` method
with Mock + OpenAI implementations (default selector model
`gpt-4o-mini`, JSON mode, temperature=0, max_tokens=256). New
`memdir.py` module: `scan_memory_files`, `format_memory_manifest`,
`collect_recent_successful_tools`, and the verbatim
`SELECT_MEMORIES_SYSTEM_PROMPT` constant from the TS source.
`SelectorError` exception on failure modes.

**M7 (sideQuery wiring)**: `find_relevant_memories` with 4 gates
(enabled / non-empty / multi-word / <60KB session bytes), filename
validation against scan manifest. `read_memories_for_surfacing` with
≤200 lines + ≤4KB per file truncation and staleness-aware header.
Inject as `<system-reminder>`-wrapped ATTACHMENT messages in `run()`
and `run_stream()`. Selector errors → Jaccard fallback. Tracer emits
on the existing `memory_select` channel.

# Risks / known unknowns

1. **frontmatter parser fail-soft is mandatory** — broken YAML must
   yield `description=None`, not raise. M1 test matrix must include
   torn frontmatter, missing keys, oversize frontmatter (>30 lines).
2. **Mixed `.json` and `.md` during the migration window** — until the
   user runs `migrate-format`, `ProjectMemory.all()` must read both.
   M1 keeps the dual-read code; a follow-up initiative can remove it
   after the user has migrated.
3. **gpt-4o-mini JSON mode occasionally emits non-JSON text** —
   `call_selector` must catch and the caller must fall back to Jaccard.
   M6 test matrix includes a "malformed JSON" scripted response and an
   "API error" scripted response; M7 test matrix includes a "selector
   returns hallucinated filename" case.
4. **Extraction subloop costs main-model tokens** — M5 default
   `--extract-memories` is OFF; user opts in. Throttle env knob exists.
   `/stats` shows `extract_invocations` so users can see cost.
5. **Main agent could mass-overwrite memories via upsert** — M2 does
   NOT expose delete; the tool is upsert-only. Delete remains
   CLI-only (`simple-agent memory delete`). A future REPL `/forget`
   command is out of scope for this initiative.
6. **Prompt cache breakage if M3 teaching section is dynamic** — the
   teaching text is fully static; the only per-turn dynamic part is
   the `## Memory` snippets block, which comes AFTER the teaching, so
   the cache prefix length stays stable.
7. **per-turn quota state leak across CLI turns** — M2's
   `_memory_writes_this_turn` MUST reset at the start of `run()` /
   `run_stream()`. Covered by an explicit test.
8. **At-least-once cursor on extraction failure** — M5's
   `_last_memory_message_uuid` must NOT advance if `Runner.run()`
   raises. Covered by an explicit test.
9. **OpenAI provider tool-calling on DashScope / qwen** — the
   write_memory_entry tool joins the schema sent to every provider.
   ctx-mgmt-pdf-align already validated DashScope qwen3.6-plus emits
   real tool_use for `snip_history`, so adding one more tool to the
   schema is low risk — but smoke-test once with the real provider
   before declaring M3 complete.

# Out of scope (this initiative)

- **M-ε**: threading-based async sideQuery — a separate follow-up initiative
- **CLAUDE.md loader enhancements** (managed / local / rules layers)
- **Auto-Dream / periodic memory consolidation**
- **SessionMemory upgrades** (the per-session in-memory store stays as-is)
- **True multi-process forked agents** (we use an in-process Runner)
- **Prompt-cache cacheSafeParams** beyond cache-friendly section ordering
- **KAIROS / TEAMMEM routing**
- **Removing `auto_learn.detect_cue`** — it coexists as a user-facing
  fallback hint (Chinese/English cue prompts) and is orthogonal to the
  new write/extract paths
- **REPL `/forget <id>` slash command** — delete-from-conversation surface
  is deferred; `simple-agent memory delete` is the only delete path
- **PyYAML dependency** — hand-rolled mini parser only

# Anything else

Companion plan file: `~/.claude/plans/auto-memory-gentle-catmull.md`.
It carries the full milestone rationale, DAG, source-code references
(`claude-code-source-code/src/memdir/*.ts`, `findRelevantMemories.ts`,
`extractMemories.ts`), explicit per-milestone test predictions, and the
five-section verbatim extraction prompt template. Each `notes:` block
above points back to the relevant section of that file for fast lookup
during implementation.

pytest baseline at initiative start: **710 passing** (1 pre-existing failure
in `test_null_tracer_zero_overhead`, baseline commit `6aed9ec`). Predicted
final pytest count: **≥768 passing** (+10 / +7 / +5 / +8 / +9 / +10 / +9
= +58 minimum, distributed across M1–M7).

> SIZING WAIVED: none. All 7 milestones are below the 4-trigger water
> mark by design (single-concern split). The largest is M1 at 3 source
> files + ~10 new tests + heavy edits to one file (memory.py).
