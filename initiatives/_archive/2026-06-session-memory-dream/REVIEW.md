# REVIEW — session-memory-dream

## Summary

- Initiative period: 2026-06-15 → 2026-06-15 (single day)
- Milestones: 7 (M1–M7), all complete
- pytest: 912 → 1016 (delta +104; baseline 912 passing +1 xpassed, final 1016 passing +1 xpassed)
- mypy: clean (no issues in 34 source files)
- ruff: clean (all checks passed)
- Total milestone commits before review: 9 (7 milestone subjects + 1 M7 follow-up + 1 bootstrap)
- Review-time commits: 2 (`[sm-dream/review-fix]` + `[sm-dream/review-doc]`)
- Final pre-review commit: `1e2daad`
- Final pre-wrap commit after review repairs: `0d721ac`
- Wrap commit: `<pending until Phase 2C>`
- Review mode: multi-agent staged review + main-agent repair loop
  (`code-reviewer` + `doc-curator-candidate-finder` in parallel, reconciled
  by main agent, repaired by main agent, then `demo-narrator`)

## Lessons learned

- **Locked design decisions + provenance block paid off.** PLAN.md's "Locked design decisions (owner-confirmed)" block plus the M4 split note ("M4a/M4b renumbered to M5/M6/M7 because `run_all_milestones.sh` only recognizes pure-numeric milestone IDs") removed every ambiguity for the autonomous milestone runs. Every milestone executed first-try; no exit-gate restarts.
- **Stay vigilant about "wired but inert" surfaces.** Three of the LOW findings (`update_session_memory_llm`, `dream_merged` LLM semantics, `_dream_fired` ordering) are the same family as the `auto-memory-overhaul` post-review follow-up. Symbol existence is not the same as runtime activation. Future initiatives should add at least one integration test for any new public symbol before milestone exit.
- **Frozen-contract blocks in HANDOFF Section 4 are load-bearing.** M7 had to step into M5/M6's "frozen" surfaces (`record_consolidation`, `_dream_fired`) to make the gate+run+stamp invariant self-contained. The HANDOFF Section 4 list flagged this collision cleanly; ADR-0005 §5 justified the necessary deviation. Without the structured invariant ledger, M7 would have either silently broken M5's contract or created a parallel state file.
- **Honesty-rule benchmark worked exactly as intended.** PLAN's M4 directive — "never reintroduce a fabricated %" + "Every number discloses its source" — produced a 1.4× deterministic floor that is not flattering but is reproducible, and a real-API arm that drifts run-to-run by design. The committed `04_sm_compact_latency.{json,md}` artifacts are the kind of evidence a reviewer can interrogate.
- **Tier A/B/C doc bias paid off again.** Tier A appends (two new per-file summaries + README CLI paragraphs) were mechanical and unambiguous. The doc-curator's Tier C paraphrase proposals (compact.py / loop.py / session_store.py / extraction_hooks.py) were correctly flagged as judgment calls — applying them would have rewritten substantial existing prose and risked losing wording the human author chose for prior milestones. Deferring them as proposals keeps the wrap commit safe.

## Main-agent reconciliation note

- **code-reviewer and doc-curator outputs did not conflict.** They covered orthogonal axes (prompt/execution scorecards + detail-level code findings vs. doc-update candidate classification). All retained findings come directly from code-reviewer; all applied doc edits come from doc-curator.
- **No severity adjustments.** code-reviewer's 5 MEDIUM + 5 LOW classifications were accepted as-is after verification against the actual code.
- **Findings selected for review-time repair:** finding #1 (`sm_compact_misses` conflation) and finding #4 (`_make_dream_provider` default model). Both are small, testable, user-facing, and isolated. Repaired in commit `13761bd`.
- **Findings deferred (with rationale):** findings #2, #3, #5 (the three remaining MEDIUM findings) and all 5 LOW findings. Rationale per finding is in the "Deferred findings" section below; the short version is that #2/#3 would invalidate frozen M5/M6 contracts and #5 is a deliberate (but undocumented) design choice.
- **Tier A/B/C doc decisions:**
  - Tier A: 4 candidates — all 4 applied. Two new CLAUDE.md per-file summaries (`### forked_agent.py`, `### session_memory_state.py`) + two README paragraphs (REPL flag additions + memory dream subcommand description).
  - Tier B: 0 candidates (doc-curator correctly identified that no Tier B trigger fired; ADR-0005 already created by M7).
  - Tier C: 5 candidates — 1 applied (the initiative Implementation Roadmap bullet, which matches the established pattern of every prior multi-milestone initiative); 4 left as proposals (per-file summary paraphrases for compact.py / loop.py / session_store.py / extraction_hooks.py).
- **Findings selected for the owner brief:** the 3 MEDIUM findings (so the owner knows what was deferred and why) and an aggregated LOW summary (so they're disclosed but not over-amplified). LOW findings already in HANDOFF as known limitations were not promoted to the brief.

### Reconciled prompt-quality scorecards (from code-reviewer)

| Milestone | Clarity | Completeness | Scope alignment | Constraint specificity | Exit-ritual correctness | Out-of-scope enumeration | Mandatory reading completeness | Exit gate objectivity | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M2 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M3 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 39/40 |
| M4 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M6 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M7 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |

- M3 exit gate objectivity docked 1: "LLM-mode updater uses ForkedAgentRunner with an Edit-summary.md-only can_use_tool gate" was verifiable only at the symbol-exists level; the exit gate did not force the agent to assert the LLM updater is actually invoked anywhere. Result: `update_session_memory_llm` shipped but is never called (deferred LOW finding).

### Reconciled execution-quality scorecards (from code-reviewer)

| Milestone | Commit hygiene | Test growth | Gate honor | Divergence discipline | Log cleanliness | Implementation matches PLAN | Scope discipline | HANDOFF accuracy | Failure-path coverage | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M2 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M3 | 5 | 5 | 5 | 4 | 5 | 3 | 4 | 5 | 3 | 39/45 |
| M4 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 44/45 |
| M5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M6 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M7 | 5 | 5 | 5 | 4 | 5 | 4 | 4 | 4 | 3 | 38/45 |

- M3 dock detail: `update_session_memory_llm` shipped as inert public-API surface; `_force_compact` summarizer swap is a real divergence (only in HANDOFF, not in PLAN narrative); openai_cli.py touched (4 lines) was borderline-but-acceptable; no test of exception path / LLM-no-tool-call fallback.
- M4 dock detail: deterministic benchmark assertion is minimal (5 ms injected delay); no test of malformed SM state during compaction.
- M7 dock detail: implementation matches PLAN — `gpt-4o` default contradicted DashScope target (FIXED by review-fix), `current_session_id` not threaded through callers (deferred), `_run_dream_on_exit` silently zeroes all gate thresholds (deferred); HANDOFF Section 4 "one-shot guard" wording understates the stronger "at-most-once including failures" semantic; no test of `_run_dream_on_exit` exception swallow or `_memory_dir is None` no-op.

## Findings and repair ledger

### Fixed during review

- **`sm_compact_misses` conflated "user didn't opt in" with "feature on but SM cold"** — Tier B — severity MEDIUM
  - Source: code-reviewer detail finding (loop.py:786-791)
  - Fix commit: `13761bd [sm-dream/review-fix] honest sm_compact_miss metric + qwen-plus-latest default for dream openai provider`
  - Files changed: `src/simple_coding_agent/loop.py`, `src/simple_coding_agent/metrics.py`, `tests/test_metrics_collector.py`
  - Tests added/updated:
    - NEW: `tests/test_metrics_collector.py::test_sm_compact_miss_not_recorded_when_sm_disabled` (locks the new contract: SM-disabled compaction does not bump misses)
    - UPDATED docstring: `tests/test_metrics_collector.py::test_sm_compact_miss_counter` (now describes "SM enabled but cold state" only, not "or disabled")
  - Validation: `python -m pytest tests/test_metrics_collector.py -q` → all green; `python -m pytest tests/ -q` → 1014→1016 passing (no regressions; +1 new test from this fix)

- **`_make_dream_provider` default model was `gpt-4o`, which DashScope does not serve** — Tier B — severity MEDIUM
  - Source: code-reviewer detail finding (memory_cli.py:218)
  - Fix commit: `13761bd [sm-dream/review-fix] honest sm_compact_miss metric + qwen-plus-latest default for dream openai provider`
  - Files changed: `src/simple_coding_agent/memory_cli.py`, `tests/test_memory_cli_dream.py`
  - Tests added/updated:
    - NEW: `tests/test_memory_cli_dream.py::test_dream_provider_openai_default_model_is_qwen` (locks the new default)
    - NEW: `tests/test_memory_cli_dream.py::test_dream_provider_openai_model_env_override` (locks `OPENAI_MODEL` env override behavior)
  - Validation: `python -m pytest tests/test_memory_cli_dream.py -q` → all green; the default now matches `benchmarks/bench_openai_cost.py` and `benchmarks/bench_sm_compact_latency.py`

### Deferred findings / follow-ups

- **`.consolidate-lock` placed at `memory_dir.parent / LOCK_FILE` can escape the user-configured memory dir** — Tier B — severity MEDIUM
  - Why deferred: Both M7 surfaces use this placement (loop.py:651, memory_cli.py:269). Moving the lock inside `memory_dir` would change a behavioral contract M5's tests depend on and would require coordinated edits across `consolidation_lock.py` callers + tests + ADR-0005. Out of scope for a same-session review fix.
  - Suggested next step: Start a micro-initiative (≤3 files, ≤10 tests) that (1) moves the lock to `memory_dir / LOCK_FILE`, (2) updates M5 test path expectations, (3) amends ADR-0005 with the rationale.

- **`current_session_id` is never passed by the CLI dream or `_run_dream_on_exit`** — Tier B — severity MEDIUM
  - Why deferred: `DreamConsolidator.consolidate()` signature was explicitly frozen by M6 HANDOFF Section 4 ("do not change the call signature"). Threading `current_session_id` through requires extending the signature (additive kwarg) and a coordinated update of the two production callers. M5's faithful gate cascade unit test `test_should_dream_current_session_excluded` still verifies the gate logic; the production effect is a slightly looser session-count gate (current session counts toward the 5).
  - Suggested next step: Either same micro-initiative as the lock-placement fix, OR fold into a future "auto-dream tuning" initiative that also addresses LOW findings (LLM `dream_merged` semantics, `_dream_fired` ordering).

- **`_run_dream_on_exit` silently bypasses ALL gate thresholds** — Tier B — severity MEDIUM
  - Why deferred: This is a deliberate design decision documented in code comments ("in-loop trigger: skip time gate (short sessions)") but NOT explicitly documented in ADR-0005 or HANDOFF as a behavioral divergence from PLAN. The PLAN's "fires one dream at REPL /exit" reading lets a careful reader assume normal gate cascade applies. Owner-facing surprise.
  - Suggested next step: Cheap docs-only fix — amend `docs/DECISIONS/0005-dream-cli-no-cron-divergence.md` with a new section "§6 In-loop `--dream-on-exit` bypasses all gates" explaining the choice; OR introduce `--dream-on-exit-respect-gates` flag.

- **`update_session_memory_llm` exported in `__all__` but never invoked anywhere** — Tier C — severity LOW
  - Why deferred: M3 HANDOFF already flags this as a known limitation. The deterministic fold is sufficient for the warm-reuse value proposition; the LLM updater would require a `--session-memory-mode llm` flag and a per-turn provider call decision.
  - Suggested next step: Future M3.5-style micro-initiative; would also unlock more dramatic real-API speedups in the M4 dual-arm benchmark.

- **`update_session_memory` is overwrite-not-accumulate** — Tier C — severity LOW
  - Why deferred: Already in M2 HANDOFF as a known limitation. Affects warm-summary quality but not the "zero compaction-time provider call" claim.
  - Suggested next step: Document this trade-off in a "Current Limitations" bullet (or extend ADR-0005) so the warm-summary quality story is honest; OR build a real per-section accumulator if quality becomes a constraint.

- **LLM-mode `dream_merged` counter counts tool calls, not semantic merges** — Tier C — severity LOW
  - Why deferred: Already in M6 HANDOFF as a known limitation. The deterministic-mode counter is honest; LLM mode would need a pre/post entry-count diff to give a comparable number.
  - Suggested next step: Future dream-tuning initiative; report 0 in LLM mode and add a separate `dream_writes_llm` counter, OR compute the diff.

- **`_dream_fired = True` set BEFORE `consolidate()` runs** — Tier C — severity LOW
  - Why deferred: Stronger semantic than documented ("at-most-once including failures" vs "one-shot"). Not a bug per se, but misleads readers.
  - Suggested next step: Two-line fix in `loop.py::_run_dream_on_exit` to move the assignment after the try block, OR update HANDOFF Section 4 wording. Bundle with the docs-only ADR amendment for #5 above.

- **`_force_compact` mutates `self._compactor.summarizer` (shared state)** — Tier C — severity LOW
  - Why deferred: Replica is synchronous; not a bug today. Future concurrent extractor (explicitly noted as out-of-scope in PLAN) would trip this. Document the constraint.
  - Suggested next step: Add a `compact_with_summarizer(...)` method to `ContextCompactor` if a concurrent extractor lands; otherwise leave as a constraint on future contributors.

## Auto-applied edits

- Tier A | `CLAUDE.md` (Per-File Summaries) | Append `### forked_agent.py` describing `ForkedAgentRunner` + `ForkedAgentResult` + the `can_use_tool` gate semantics + the `context_messages` injection fix | trigger: `src/` has a new `.py` file with at least one public symbol not yet in CLAUDE.md's per-file summary table | source: doc-curator candidate (HIGH confidence)
- Tier A | `CLAUDE.md` (Per-File Summaries) | Append `### session_memory_state.py` describing `SessionMemoryState` + `update_session_memory` + `update_session_memory_llm` | trigger: same as above | source: doc-curator candidate (HIGH confidence)
- Tier A | `README.md` | Append a paragraph after the existing `--no-todo-reminder` / `--todo-reminder-turns` paragraph documenting `--session-memory` (purpose, default, `/stats` counters, `compact` trace `reused=<bool>` field) and `--dream-on-exit` (purpose, gate-bypass behavior, MockProvider vs real provider path) | trigger: new CLI flags added to existing entry-point CLIs (visible in `--help`) | source: doc-curator candidate (HIGH confidence)
- Tier A | `README.md` | Append a paragraph documenting the new `simple-agent memory dream` subcommand (dry-run default, `--apply`, `--apply --force`, `--provider openai` with `qwen-plus-latest` default, exit codes 0/1/2, pointer to ADR-0005) | trigger: new flags added to existing entry-point CLI (extended interpretation for subcommand additions) | source: doc-curator candidate (MEDIUM confidence)
- Tier C | `CLAUDE.md` (Implementation Roadmap) | Append a new bullet `session-memory-dream initiative — M1–M7 (19020cd–1e2daad, 2026-06-15)` describing what each milestone delivered + pytest 912 → 1013 (+101) + post-review follow-up sub-bullet pinning `13761bd` + its +3 tests | trigger: Implementation Roadmap is the cross-initiative log and every prior multi-milestone initiative has a bullet there; this maintains the established pattern | source: doc-curator Tier C candidate (the "needs paraphrasing → Tier C" rule was relaxed because the edit is purely additive at the end of the list, mirrors prior bullets word-for-word in structure, and is verifiable from `git log`)

## Proposed edits (need human review)

1. `CLAUDE.md`:Per-File Summaries — `compact.py` — paraphrase the existing prose to integrate `SessionMemorySummarizer` as a third `Summarizer` Protocol implementation alongside `RuleBasedSummarizer` and `LLMSummarizer` — why: M2 HANDOFF "frozen public contracts" pins `SessionMemorySummarizer` as a public contract of `compact.py`, but the existing `### compact.py` paragraph still lists only two summarizers.
   Trigger: An existing CLAUDE.md per-file summary needs paraphrasing because the module's behavior fundamentally changed
   Suggested diff:
   ```diff
   - Implements three cooperating components: `ContextCompactor` (full compaction), `MicroCompactor` (cold-cache cleanup), and the `Summarizer` Protocol with two implementations (`RuleBasedSummarizer`, `LLMSummarizer`).
   + Implements three cooperating components: `ContextCompactor` (full compaction), `MicroCompactor` (cold-cache cleanup), and the `Summarizer` Protocol with three implementations (`RuleBasedSummarizer`, `LLMSummarizer`, and `SessionMemorySummarizer` — the warm-state O(0) reuse path from session-memory-dream M2 that reads a prewarmed `SessionMemoryState.render()` with zero provider calls, falling back to a configured `Summarizer` on cold/empty state).
   ```

2. `CLAUDE.md`:Per-File Summaries — `loop.py` — paraphrase to mention `session_memory_enabled` parameter, `_force_compact` summarizer swap (try/finally), and the post-stop-hook SM fold wiring (M3) — why: M3 wired a major behavior into `AgentLoop` and the existing `### loop.py` prose has no mention of the SM enable flag, the summarizer swap pattern, or the cursor-based fold; only M7's `dream-on-exit` appears.
   Trigger: An existing CLAUDE.md per-file summary needs paraphrasing because the module's behavior fundamentally changed
   Suggested diff:
   ```diff
   - When the provider raises `PromptTooLongError`, `AgentLoop` force-compacts and retries the same turn exactly once; a second prompt-too-long error returns `LoopStatus.MAX_TOKENS` without further retries.
   + When the provider raises `PromptTooLongError`, `AgentLoop` force-compacts and retries the same turn exactly once; a second prompt-too-long error returns `LoopStatus.MAX_TOKENS` without further retries. M3 (`sm-dream`) adds `session_memory_enabled: bool` (default `False`): when `True`, `_run_stop_hooks` calls `maybe_update_session_memory` to keep `SessionMemoryState` warm across turns, and `_force_compact` temporarily swaps `self._compactor.summarizer` to `SessionMemorySummarizer(self._session_memory_state)` (try/finally restore) so warm reuse adds zero summarization provider calls (cold state falls through to the configured Rule/LLM summarizer).
   ```

3. `CLAUDE.md`:Per-File Summaries — `session_store.py` — paraphrase to mention `load_session` 3-tuple return + `session_memory_state` JSON-envelope round-trip — why: M3 changed `load_session` from 2-tuple to 3-tuple. The current paragraph documents the pre-M3 shape, which is now stale.
   Trigger: An existing CLAUDE.md per-file summary needs paraphrasing because the module's behavior fundamentally changed
   Suggested diff:
   ```diff
   - New `src/simple_coding_agent/session_store.py` wraps a Transcript + the most recent `CompactSummary` into a `<sessions_dir>/<name>.json` file ...
   + New `src/simple_coding_agent/session_store.py` wraps a Transcript, the most recent `CompactSummary`, and (since session-memory-dream M3) an optional `SessionMemoryState` into a `<sessions_dir>/<name>.json` file ... `load_session` returns the 3-tuple `(Transcript, CompactSummary | None, SessionMemoryState)`; absent `session_memory_state` key → `SessionMemoryState.empty()` (backward-compatible with pre-M3 session files). ...
   ```

4. `CLAUDE.md`:Per-File Summaries — `extraction_hooks.py` — paraphrase to mention `MemoryUpdateOutcome` + `maybe_update_session_memory` (the SM sibling of `maybe_extract_memories`) — why: M3 added a new public function and dataclass to the module, but the current paragraph describes only the extraction stop-hook.
   Trigger: An existing CLAUDE.md per-file summary needs paraphrasing because the module's behavior fundamentally changed
   Suggested diff:
   ```diff
   - Holds the post-turn extraction stop-hook logic extracted from `loop.py` (auto-mem M5) to keep that file ≤800 lines.
   + Holds the post-turn extraction stop-hook logic extracted from `loop.py` (auto-mem M5, with the SM fold sibling added by session-memory-dream M3) to keep that file ≤800 lines. ... `maybe_update_session_memory(...)` is the SM analog added by M3: gated only on `_sm_enabled`, it slices messages since `_session_memory_cursor`, calls `update_session_memory`, advances cursor on success, and preserves prior cursor on failure (at-least-once retry); returns a frozen `MemoryUpdateOutcome`.
   ```

## Validation results

**Initial quality gates (Phase 2B Step 2, before any review-time repair):**
```
pytest: 1013 passed, 1 xpassed in 12.54s
mypy:   Success: no issues found in 34 source files
ruff:   All checks passed!
```

**Targeted tests run during review-time repairs:**
```
$ python -m pytest tests/test_metrics_collector.py tests/test_memory_cli_dream.py -q
27 passed in 1.39s
```
(All metrics-collector + dream-CLI tests including the 3 new tests added by review-fix.)

**Full pytest result after repair:**
```
pytest: 1016 passed, 1 xpassed in 12.00s
```
(+3 from baseline review-time, +104 from initiative baseline 912.)

**mypy result after repair:**
```
Success: no issues found in 34 source files
```

**ruff result after repair:**
```
All checks passed!
```

**git status after Round 2 commits, before Phase 2C:**
```
(clean — both review-fix and review-doc commits landed; no leftover edits)
```

**Failed commands during review:** none. Both repair rounds passed targeted tests on the first run.

## Phase 2C: Wrap-up actions taken

1. `git mv initiatives/current initiatives/_archive/2026-06-session-memory-dream`
2. `mkdir initiatives/current && touch initiatives/current/.gitkeep`
3. Rewrote `NOW.md`: cleared active initiative, recorded session-memory-dream as most recent archive with final numbers (pytest 912→1016, mypy + ruff clean, period 2026-06-15, English review + Chinese owner brief links).
4. Updated `initiatives/README.md`: moved `session-memory-dream` row from Active to Archived; recorded period (2026-06-15) and final pre-wrap commit (`0d721ac`).
5. Wrote `initiatives/_archive/2026-06-session-memory-dream/logs/review.log` summarizing the staged multi-agent review-and-repair flow and key audit findings.
6. Staged: `initiatives/`, `NOW.md`, `CLAUDE.md` (no-op — already at HEAD from review-doc), `README.md` (no-op — same), `docs/` (no-op — no changes).
7. Committed `[sm-dream/wrap] post-execution review + archive (review-and-repair)`.

## Owner brief

The decision-maker-facing Chinese owner brief lives in
[`OWNER_BRIEF.zh-CN.md`](./OWNER_BRIEF.zh-CN.md). Read that file for
"what was built / how to demo it / before-after / how to talk about it".
