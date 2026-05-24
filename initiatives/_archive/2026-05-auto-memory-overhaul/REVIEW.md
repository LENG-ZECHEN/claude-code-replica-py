# REVIEW — auto-memory-overhaul

## Summary

- Initiative period: 2026-05-24 16:06 -> 2026-05-24 19:07 (single day, ~3h)
- Milestones: 7 (M1–M7), all complete
- pytest: 711 -> 807 (delta **+96**; baseline 711 per PROGRESS.md, or 710 passing + 1 env-sensitive failure per PLAN provenance — see reconciliation note). Final suite: **807 passed, 0 failed, 0 skipped**.
- mypy: clean (26 source files)
- ruff: clean
- Total commits in this initiative (`6aed9ec..HEAD`): **10** (bootstrap `36cd7ba`; M1 `612487d` + exit-ritual `927be03` + fix `3aa6696`; M2 `8c230ca`; M3 `89ee8b4`; M4 `7830075`; M5 `99afe34`; M6 `272e831`; M7 `e9aef6a`)
- Final pre-wrap commit: `e9aef6a` (`[auto-mem/M7]`)
- Review mode: multi-agent staged review (`code-reviewer` + `doc-curator-candidate-finder` in parallel, reconciled by the main agent, then `demo-narrator`)

## Follow-up resolution (added 2026-05-25, post-archive by owner request)

The findings below were acted on after this initiative was archived. The
original review text (scorecards, findings, decisions) is preserved verbatim
as the historical record; this section records current status.

| Finding | Sev | Status |
|---|---|---|
| `recent_tools` always `[]` in the live loop | MEDIUM | ✅ fixed `212b6af` — inject scans the transcript excluding the trailing current-turn user message |
| `read_file_state` never populated | MEDIUM | ✅ resolved `212b6af` — unused parameter removed (memory-id vs workspace-path namespaces never matched) |
| `extraction_in_progress` gate dead code | MEDIUM | ✅ fixed `212b6af` — `_run_stop_hooks` passes the loop's real flag (captured before in-progress is set) |
| `memory_select` trace `fallback_used` / `manifest_size` wrong | MEDIUM | ✅ fixed `212b6af` — `find_relevant_memories` returns `RecallResult` carrying real values |
| `ExtractMemoriesRunner` M4 manifest stub | LOW | ✅ fixed `212b6af` — uses `format_memory_manifest(scan_memory_files())` |
| `write_memory_entry` `tags` dropped on persistence | LOW | ✅ fixed `212b6af` — `tags` round-trips through `.md` frontmatter |
| manifest 25 KB cut char-indexed | LOW | ✅ fixed `212b6af` — byte-accurate truncation |
| `provider.py` 867 > 800-line limit | LOW | ⏸ not addressed (no behavioral impact; deferred) |
| stale `test_null_tracer_zero_overhead` claim | LOW | ⏸ HANDOFF/PLAN are archived snapshots; left as-is |

Each fix shipped with a test exercising the integrated turn path (the gap that
let these ship green). pytest 807 → 816 (+9); mypy + ruff clean; `loop.py` still
800 lines. Living docs were synced in `8d20b1b` (CLAUDE.md roadmap + per-file
summaries, README module lists, `docs/memdir.md`, ADR-0003) and `c373ee1`
(NOW.md). Of the Tier C "Proposed edits" below, the roadmap entry (#1) and the
README module rows (#2) were applied in `8d20b1b`; the `migrate-format` README
note (#3) is still open.

## Lessons learned

- **The single biggest pattern this initiative should teach future bootstraps: "passing tests ≠ working feature."** Four read-path features (recent-tools-aware selection, read-file dedup, the `extraction_in_progress` re-entrancy gate, and the `fallback_used` trace) pass unit tests because the tests call the pure functions with crafted inputs — but they are inert in the integrated turn loop. Milestone prompts should require at least one *end-to-end* assertion per wired feature (e.g. "assert `recent_tools != []` through the real `run()` path"), not only direct unit tests of the pure function.
- **Pre-splitting M-α′/M-γ/M-β into 7 single-concern milestones worked.** Every milestone stayed under the sizing water marks, no thrash-loop termination occurred, and test growth was steady (+13/+10/+5/+11/+18/+16/+23). The DAG note in PLAN.md made the linear M1→M7 order auditable.
- **File-size budget enforcement was inconsistent.** M5/M7 disciplined `loop.py` to ≤800 lines by extracting `extraction_hooks.py` / `recall_hooks.py`, but M6 pushed `provider.py` to 867 lines (over the same hard limit) with no waiver. Future prompts should pre-flag the headroom of *every* file a milestone touches, not just the headline file.
- **HANDOFF accuracy drifted in two places** (the inaccurate "outer check" claim for the extraction re-entrancy guard, and the stale `test_null_tracer_zero_overhead` "failing" note). Exit rituals should re-verify Section 3 numbers and Section 2 design-decision claims against the actual diff, not narrate intent.
- **`migrate-format` + dual-read compat window is a clean zero-downtime migration pattern** worth reusing for future on-disk format changes.

## Main-agent reconciliation note

- **Did the two Stage A subagents conflict?** No. `code-reviewer` scored prompts/execution + surfaced 9 detail findings; `doc-curator-candidate-finder` classified doc candidates. The only overlap was the stale `test_null_tracer_zero_overhead` claim, which the code-reviewer (correctly) framed as a doc-risk finding rather than a doc edit — no contradiction.
- **Detail findings:** all 9 retained. No deduplication needed (each cites a distinct location). No severity adjustments — I independently re-read the code and confirmed every finding at its cited line (`loop.py:198/209/216/369/541/548/558`, `recall_hooks.py:48/59-65`, `extraction_hooks.py:121`, `provider.py` 867 lines, `extract_memories.py:84-89`, `memory.py:197-207`). The `demo-narrator` further confirmed all 9 by live run. None were rejected as unsupported.
- **Scorecards:** used `code-reviewer`'s numbers verbatim; found no contradiction with the mandatory files, so no corrections were applied. The lowest prompt total (M7, 37/40) and lowest execution total (M7, 41/45) both trace to the same root cause — M7's prompt specified `fallback_used=True` and threaded `recent_tools`/`read_file_state` without specifying *where* they are computed, which produced the inert wiring.
- **Doc-update decisions** (see "Auto-applied edits" and "Proposed edits"):
  - **Tier A — APPLIED both.** (1) README flag paragraph for `--extract-memories` / `--extract-throttle`. (2) Four `### <module>` per-file summaries appended to CLAUDE.md. **This (2) overrides the doc-curator's cautious downgrade of the per-file summaries to Tier C.** Rationale: the RUNBOOK Tier A table row explicitly classifies "new `.py` file with a public symbol not yet in CLAUDE.md's per-file summary → append a `### <filename>` section" as Tier A append-only; the target "## Per-File Summaries" section is NOT the protected "Implementation Roadmap" section; and the modules were well-understood (I read all four in full). The doc-curator itself offered this as option (a). I judged the appends mechanical-enough and wrote accurate, caveat-bearing summaries.
  - **Tier B — APPLIED both, with one consolidation.** (1) The doc-curator raised 3 separate subsystem-doc candidates (`memdir.py`, `extract_memories.py`, `extraction_hooks.py`); I **consolidated them into a single `docs/memdir.md`** covering the whole memory recall+extraction subsystem, per the doc-curator's own cohesion recommendation and to avoid fragmentation/drift across 3 overlapping docs. `recall_hooks.py` (80 LOC, 1 symbol) did not meet the Tier B threshold and was folded into the same doc. (2) Created `docs/DECISIONS/0003-provider-selector-and-hook-module-extraction.md` + index row.
  - **Tier C — PROPOSED only (not applied):** 3 proposals (below).
- **Owner-facing findings selected for the Chinese brief:** all 4 MEDIUM "inert-wiring" findings + the `tags`-dropped, manifest-stub, provider.py-size, and stale-test-claim LOW findings, plus the 3 pending Tier C proposals. Bookkeeping noise (commit-subject formatting, test-count arithmetic) was excluded.

### Reconciled prompt + execution scorecards (from `code-reviewer`)

## Phase 2B-3: Prompt quality scorecards

| Milestone | Clarity | Completeness | Scope alignment | Constraint specificity | Exit-ritual correctness | Out-of-scope enumeration | Mandatory reading completeness | Exit gate objectivity | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M2 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M3 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M4 | 5 | 5 | 5 | 4 | 5 | 5 | 5 | 5 | 39/40 |
| M5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 39/40 |
| M6 | 5 | 5 | 5 | 4 | 5 | 5 | 5 | 5 | 39/40 |
| M7 | 5 | 5 | 4 | 4 | 5 | 5 | 5 | 4 | 37/40 |

No row fell below 36/40. Notable docked dimensions (each traces to a downstream execution gap):
- **M4 — Constraint specificity (4)**: sanctioned the `_get_existing_manifest` stub but obligated no later milestone to replace it → orphaned stub with no owner.
- **M5 — Exit gate objectivity (4)**: the `extraction_in_progress` gate is listed as a verifiable layer, but the prompt's own implementation note describes a flag the gate function can't read → a test can pass while the layer is inert (which is what happened).
- **M6 — Constraint specificity (4)**: repeated the ≤800-line rule for `memdir.py` but said nothing about `provider.py` (started at 792); adding `call_selector` predictably breached 800.
- **M7 — Scope alignment / Exit gate objectivity / Constraint specificity (4/4/4)**: the exit gate requires `fallback_used=True` emission, but the prompt's API sketch returns `list[MemoryHeader]` with no fallback signal, making it unimplementable as specified; `recent_tools` / `read_file_state` are threaded without specifying where they are computed or who populates them → two features wired but inert.

## Phase 2B-4: Execution quality scorecards

| Milestone | Commit hygiene | Test growth | Gate honor | Divergence discipline | Log cleanliness | Implementation matches PLAN | Scope discipline | HANDOFF accuracy | Failure-path coverage | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 44/45 |
| M2 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M3 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 44/45 |
| M4 | 5 | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 5 | 44/45 |
| M5 | 5 | 5 | 5 | 4 | 5 | 4 | 5 | 4 | 5 | 43/45 |
| M6 | 5 | 5 | 4 | 5 | 5 | 4 | 4 | 5 | 4 | 42/45 |
| M7 | 5 | 5 | 5 | 5 | 5 | 3 | 5 | 4 | 4 | 41/45 |

No row fell below 40.5/45. Most material deductions:
- **M1 — Scope discipline (4)**: commit `612487d` also modified `tests/test_memory_cli.py`, `tests/test_openai_cli_repl.py`, `tests/test_repl_slash_remember.py` (necessary `.md`-format fixups) without the deviation being noted in HANDOFF (M1 lists "deviations: (none)").
- **M5 — Divergence/Implementation/HANDOFF (4/4/4)**: the `extraction_in_progress` gate is non-functional; HANDOFF frames it as a deliberate "outer check" design that does not exist in code. Re-entrancy is actually protected only by gate 1 (`is_subloop`).
- **M6 — Gate honor/Scope/Failure-path (4/4/4)**: `provider.py` grew 792 → 867, breaching the 800-line hard limit with no waiver.
- **M7 — Implementation matches PLAN (3)**: the single biggest "passing tests ≠ working feature" gap — `recent_tools` always `[]`, `read_file_state` never populated, `fallback_used` always `False` in the integrated loop.
- **Cross-cutting (Log cleanliness)**: every `M{N}.log` is a 1–19-line final-summary capture (harness artifact), so intermediate RED→GREEN/TDD ordering is not observable from the logs. Nothing anomalous appears; scored 5 but flagged that the logs cannot positively confirm TDD-first ordering.

### Reconciled detail-level findings (all 9 retained; all independently verified)

> **Status (2026-05-25):** the 4 MEDIUM findings plus the manifest-stub, `tags`,
> and byte-truncation LOW findings were fixed on `main` (`212b6af`) — see
> **Follow-up resolution** near the top. The `provider.py` size and
> stale-test-claim LOW items remain unaddressed. Original finding text is
> retained verbatim below.

- **`extraction_in_progress` re-entrancy gate is dead code** — `loop.py:541-558` / `extraction_hooks.py:121` — **MEDIUM**
  - **What**: `_run_stop_hooks` sets `self._extraction_in_progress = True` then calls `maybe_extract_memories(..., extraction_in_progress=False, ...)` with a hardcoded `False`; gate 4 checks the passed-in literal, never the instance flag.
  - **Why it matters**: One of the 7 named gating layers is non-functional; only gate 1 (`is_subloop`) guards re-entrancy. HANDOFF documents an "outer check" that does not exist.
  - **Fix sketch**: Pass `extraction_in_progress=self._extraction_in_progress` (set before the call), or drop the flag and rely on `is_subloop`; correct the HANDOFF claim.

- **`recent_tools` is always empty in the live loop** — `loop.py:209/216/369` + `recall_hooks.py:48` — **MEDIUM**
  - **What**: `inject_memory_attachments` runs immediately after the new user message is appended, so `collect_recent_successful_tools` reverse-scans, hits that fresh user-text message first, and returns `[]` every turn.
  - **Why it matters**: The verbatim `SELECT_MEMORIES_SYSTEM_PROMPT` "recently-used tools" clause can never trigger end-to-end; exercised only by unit tests with hand-built transcripts.
  - **Fix sketch**: Compute `recent_tools` from the transcript as of the previous turn (before appending the new user input), or skip a trailing user-text message before scanning.

- **`read_file_state` dedup set is never populated** — `loop.py:198` (init, no writer) — **MEDIUM**
  - **What**: `self._read_file_state` is threaded into `find_relevant_memories` as a dedup filter but nothing ever adds to it.
  - **Why it matters**: PLAN M7's "deduplicates against files the main agent has already Read" can never fire; a memory already opened via `read_file` can still be re-surfaced.
  - **Fix sketch**: Populate `_read_file_state` from `read_file` successes each turn (note: memory-id vs workspace-path namespaces differ and need reconciling), or drop the parameter and document the omission.

- **`memory_select` trace always reports `fallback_used=False` and a mislabeled `manifest_size`** — `recall_hooks.py:59-65` — **MEDIUM**
  - **What**: The Jaccard fallback happens inside `find_relevant_memories` (returns only `list[MemoryHeader]`); the caller hardcodes `fallback_used=False` and sets `manifest_size=len(headers)` (== `selected_count`), not the scanned manifest size.
  - **Why it matters**: PLAN M7 and the exit gate require the fallback path to emit `fallback_used=True`; the trace is wrong on every selector failure, defeating the cost/diagnostic purpose. No test asserts these values.
  - **Fix sketch**: Return `(headers, fallback_used)` (or a small result object) from `find_relevant_memories`; emit the real scanned-manifest length.

- **`provider.py` exceeds the 800-line hard limit** — `provider.py` (867 lines; 792 at baseline, pushed over by M6 `272e831`) — **LOW**
  - **What**: CLAUDE.md and every prompt pin "files ≤800 max"; M6 added `call_selector` + `SelectorError` without extracting.
  - **Why it matters**: Violates the project's own size invariant, inconsistent with the lengths M5/M7 went to for `loop.py`.
  - **Fix sketch**: Extract selector/JSON-mode logic into a `selector.py`, or split the OpenAI conversion helpers out of `provider.py`.

- **`ExtractMemoriesRunner` still uses the M4 manifest stub** — `extract_memories.py:84-89, 117` — **LOW**
  - **What**: `_get_existing_manifest` reads `MEMORY.md[:2000]` (raw byte-prefix, can sever a line) instead of `format_memory_manifest(scan_memory_files(memory_dir))`, available since M6.
  - **Why it matters**: The extraction prompt's "do not duplicate" hint can be stale/garbled, so the extractor may re-save existing memories. Low because extraction is opt-in (default off) and upsert-safe.
  - **Fix sketch**: Replace the stub with the M6 canonical call (trivial now that `memdir` exists).

- **`write_memory_entry`'s `tags` parameter is silently dropped on persistence** — `memory.py:197-207` (`to_md_text`) — **LOW**
  - **What**: `MemoryEntry` carries `tags` and the tool schema accepts `tags`, but `to_md_text` does not serialize a `tags:` frontmatter key (and `to_dict` omits it too).
  - **Why it matters**: A documented tool parameter is a no-op; callers/model may believe tags persist.
  - **Fix sketch**: Serialize `tags` into frontmatter (and parse it back), or drop `tags` from the tool signature/schema.

- **Manifest 25 KB cut mixes string-index and byte-length** — `memory.py` (manifest truncation) — **LOW**
  - **What**: The cap tests `len(content.encode("utf-8")) > 25_000` but cuts with a string index, then appends a footer. With multibyte descriptions the byte length can still exceed 25 KB.
  - **Why it matters**: The "≤25 KB" guarantee can be violated for non-ASCII manifests; overshoot is bounded by one line + footer.
  - **Fix sketch**: Truncate against an encoded-bytes accumulator; compute footer-inclusive size before finalizing.

- **HANDOFF/PROGRESS claim `test_null_tracer_zero_overhead` is failing/quarantined; it passes now** — `HANDOFF.md:155,188`, PLAN provenance — **LOW (doc-risk)**
  - **What**: The full suite runs **807 passed, 0 failed, 0 skipped** in this environment; HANDOFF/PLAN describe this test as a standing failure "quarantined under coverage runs."
  - **Why it matters**: A reviewer trusting HANDOFF Section 3 would expect a known-red test that isn't red, masking either a flaky-but-green timeit test or a stale claim.
  - **Fix sketch**: Re-verify and update the provenance note; if genuinely environment-sensitive, mark it `skip`/`flaky` explicitly rather than describing it as failing in prose.

## Auto-applied edits

Applied by the MAIN REVIEW AGENT during Step 3C (logged here per RUNBOOK):

- Tier A | `README.md` | appended a paragraph documenting `--extract-memories` / `--extract-throttle` (both REPLs + env vars) after the threshold-overrides paragraph | trigger: "a new CLI flag is added to an existing entry-point CLI" | source: doc-curator candidate (HIGH)
- Tier A | `CLAUDE.md` | appended `### extract_memories.py` per-file summary to "## Per-File Summaries" | trigger: "src/ has a new .py file with a public symbol not yet in CLAUDE.md's per-file summary table" | source: doc-curator candidate downgraded to Tier C → main-agent re-promoted to Tier A (RUNBOOK explicitly classifies this as Tier A; section is unprotected; append-only)
- Tier A | `CLAUDE.md` | appended `### extraction_hooks.py` per-file summary (with inert-gate caveat) | trigger: same as above | source: main-agent inspection
- Tier A | `CLAUDE.md` | appended `### memdir.py` per-file summary | trigger: same as above | source: main-agent inspection
- Tier A | `CLAUDE.md` | appended `### recall_hooks.py` per-file summary (with inert-wiring caveat) | trigger: same as above | source: main-agent inspection
- Tier B | `docs/memdir.md` | created consolidated subsystem doc for the memory recall+extraction subsystem (covers memdir.py + extract_memories.py + extraction_hooks.py + recall_hooks.py) | trigger: "a new top-level module >150 LOC AND exporting ≥3 public symbols" (fired for memdir.py 315 LOC, extract_memories.py 233 LOC, extraction_hooks.py 155 LOC) | source: doc-curator candidates (3) consolidated into 1 by the main agent for cohesion
- Tier B | `docs/DECISIONS/0003-provider-selector-and-hook-module-extraction.md` | created ADR for the `Provider.call_selector` protocol extension + budget-driven hook-module extraction | trigger: "HANDOFF Section 2 collectively contains ≥2 divergences AND ≥1 architectural (protocol change + new abstraction)" | source: doc-curator candidate (HIGH)
- Tier B | `docs/DECISIONS/README.md` | appended ADR-0003 index row | trigger: ADR creation (index maintenance) | source: main-agent

## Proposed edits (need human review)

Tier C — NOT applied; the human applies or rejects these after reading this review.

1. `CLAUDE.md`: "Implementation Roadmap (Completed P1–P9)" section — add an `auto-memory-overhaul initiative — M1–M7` roadmap bullet (matching the format of prior initiative bullets). — why: every prior initiative has a roadmap bullet, but the RUNBOOK Tier A hard rules explicitly protect this section from auto-edits, so it must be human-applied.
   Trigger: RUNBOOK Tier C ("rewrite existing prose" + protected Implementation Roadmap section).
   Suggested diff:
   ```diff
   + - **auto-memory-overhaul initiative — M1–M7** (`612487d`–`e9aef6a`, 2026-05-24).
   +   Brings the memory subsystem to the source-code form: `.md` + YAML
   +   frontmatter entries with recursive scan + 200-line/25KB manifest truncation
   +   + `migrate-format` CLI (M1); a `write_memory_entry` tool with a per-turn
   +   quota of 3 (M2) and a static `## Memory Management` teaching section (M3);
   +   an `ExtractMemoriesRunner` 5-turn extraction subloop (M4) gated by a 7-layer
   +   stop-hook in `extraction_hooks.py` behind `--extract-memories` (M5); a
   +   `Provider.call_selector` protocol method + new `memdir.py` infra (M6); and
   +   synchronous sideQuery recall injecting `<system-reminder>` ATTACHMENT
   +   memories via `recall_hooks.py`, with Jaccard fallback (M7). See ADR-0003.
   +   Async sideQuery (M-ε) deferred; several read-path features wired-but-inert
   +   (see REVIEW.md). pytest 711 → 807 (+96), mypy + ruff clean.
   ```

2. `README.md`: "Key concepts replicated" and "Project structure" tables — add rows for the four new modules. — why: these edit existing tables (not append-only) and touch first-impression material → Tier C.
   Trigger: RUNBOOK Tier C (changes to existing README tables/structure).
   Suggested diff (Project structure block):
   ```diff
     memory.py               SessionMemory, ProjectMemory, MemorySelector (top-5 Jaccard)
   + memdir.py               scan/manifest + Provider.call_selector recall + Jaccard fallback
   + extract_memories.py     ExtractMemoriesRunner (≤5-turn post-turn extraction subloop)
   + extraction_hooks.py     7-layer stop-hook gating for auto-extraction
   + recall_hooks.py         inject sideQuery ATTACHMENT memories into the transcript
   ```

3. `README.md`: "Console scripts" area — document the `simple-agent memory migrate-format` subcommand (and the wider `memory` subcommand group). — why: no new `[project.scripts]` entry was added (only a subcommand of the existing `simple-agent memory` group), so no Tier A row matches; placing net-new prose is a judgment call → Tier C.
   Trigger: RUNBOOK Tier C (net-new prose placement; no Tier A row matches a new subcommand).
   Suggested diff:
   ```diff
   + The `simple-agent memory` subcommand group also exposes `migrate-format`,
   + which idempotently converts legacy `.json` memory entries to the
   + `.md` + frontmatter format (existing `.md` files are skipped, not overwritten).
   ```

## Phase 2C: Wrap-up actions taken

- Step 6 — `git mv initiatives/current initiatives/_archive/2026-05-auto-memory-overhaul`; recreated `initiatives/current/` with `.gitkeep`.
- Step 7 — rewrote `NOW.md` (no active initiative; auto-memory-overhaul recorded as last completed with final numbers).
- Step 8 — moved the `auto-memory-overhaul` row in `initiatives/README.md` from Active to Archived.
- Step 9 — wrote `initiatives/_archive/2026-05-auto-memory-overhaul/logs/review.log`.
- Step 10 — committed everything (this review + owner brief + archive move + NOW/README updates + Tier A/B doc edits) as `[auto-mem/wrap]`.

(Commands and final SHAs are recorded in `logs/review.log`.)

## Owner brief

The decision-maker-facing Chinese owner brief lives in
[`OWNER_BRIEF.zh-CN.md`](./OWNER_BRIEF.zh-CN.md). Read that file for
"what was built / how to demo it / before-after / how to talk about it".
