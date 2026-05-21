# HANDOFF — Next: M4

> Updated by: M3 session
> Date: 2026-05-21
> Read this file FIRST in the next session, then verify against git/pytest.

---

## 1. Objective State

> The next session MUST re-verify these numbers. Do not trust this list
> blindly — re-run the commands.

- Last commit: `910c337` — `git -C python-replica show 910c337` to inspect
- pytest: 455 passing (was 436 after M2, delta +19)
- mypy:   clean (Success: no issues found in 18 source files)
- ruff:   clean (All checks passed!)
- Branch: main

## 2. What M3 Accomplished

- C3: new `src/simple_coding_agent/metrics.py` ships
  `MetricsCollector` (mutable dataclass) with counters for
  `full_compacts`, `snip_invocations`, `microcompact_invocations`,
  `reactive_compacts`, `externalized_bytes`, and a `tokens_per_turn`
  list, plus a `format_stats()` renderer used by REPL `/stats`.
  Commit `910c337`.
- C4: `AgentLoop.__init__` accepts an optional
  `metrics: MetricsCollector | None` kwarg and bumps each counter at
  its fire site — `_force_compact` (full_compacts, covering both
  threshold and reactive paths), `_maybe_microcompact`,
  `_maybe_snip`, and an explicit `record_reactive_compact()` in the
  `PromptTooLongError` retry branch of both `run()` and
  `run_stream()`. `_refresh_externalized_bytes()` samples
  `ToolResultStore.total_externalized_bytes` after every turn so
  per-item and total-budget externalization paths are counted
  uniformly. Per-step token estimates are recorded via
  `built.estimated_tokens`. `LoopResult` gains a `metrics` field;
  `cli.py` wires a `MetricsCollector()` into every REPL-spawned loop
  and registers a `/stats` slash command (visible in `/help`) that
  prints `MetricsCollector.format_stats()`. Commit `910c337`.
- B3: `SessionMemory.dump_json(path)` + `SessionMemory.load_json(path)`
  in `memory.py`. Atomic write via `tempfile.mkstemp` + `os.replace`
  (rolling back the tempfile on failure so the prior snapshot stays
  intact). `load_json` gracefully returns an empty store on missing
  file, malformed JSON (with a warning), or unrecognized top-level
  shape; extra root-level and per-entry fields are ignored for
  forward compatibility. REPL auto-loads
  `<workspace>/.simple-agent/session_memory.json` on start (via
  `_session_memory_path(workspace)`) and auto-saves on `/exit`,
  `/quit`, or EOF; OSError during save prints a warning and exits
  cleanly. Commit `910c337`.
- Tests: `tests/test_metrics_collector.py` (8 cases — every counter,
  externalized bytes via a real `ToolResultStore` + 80k/70k/60k
  inputs, per-turn token estimate, fresh-loop reset, identity check
  on `LoopResult.metrics`); `tests/test_session_memory_persist.py`
  (9 cases — round-trip, missing file, corrupted JSON + warning,
  atomic-rename failure rollback, all four `MemoryType` values,
  forward-compat extra fields, empty store, missing parent dir,
  timestamp preservation); `tests/test_repl.py` (+2 stats cases plus
  one assertion-extension on the existing `/help` test). pytest
  436 → 455 (+19). Commit `910c337`.

## 3. Decisions Made That Diverge From Plan ⚠️

> THE MOST IMPORTANT SECTION. Any place reality diverged from
> RUNTIME_ACTIVATION_PLAN.md — alternative library, skipped test,
> renamed function, added abstraction, deferred work, etc. Include
> the WHY so the next session can decide whether to inherit or revert.
>
> If nothing diverged, write "(none)" — do NOT delete the section.

- **Added `ToolResultStore.total_externalized_bytes` (read-only
  property)**, which is a one-line additive change to an
  out-of-milestone module. Without it, `MetricsCollector` would have
  to either reach into the store's private `_stored` dict or
  duplicate the byte-accounting logic in the loop. The property is
  pure (sums `original_size` over the existing in-memory entries),
  has no side effects, and does not change any existing behavior.
  Treat it as part of the metrics surface; do not revert.
- **`tests/test_session_memory_persist.py` ships with 9 cases, not
  the 6 listed in plan section 3.2.** The extra 3 (empty-store
  round-trip, missing-parent-dir auto-create, timestamp
  preservation) close real edge cases in `dump_json` / `load_json`
  and bridge the gap to the plan's pytest target (≥455). Each is a
  surface-level invariant of the new persistence layer; no
  behavior was changed to fit the tests.
- **`MetricsCollector` is a mutable dataclass with `record_*`
  helpers, not a `@dataclass(frozen=True)` immutable record.** The
  global immutability rule in `~/.claude/rules/ecc/common/
  coding-style.md` would otherwise mandate `frozen=True`, but every
  field on the collector is by definition mutated in place (the
  whole point is to count events as they happen). The `AgentLoop`
  is the only writer, the collector is owned 1:1 by a loop instance,
  and tests verify counters reset per loop. This is the same
  pattern as `ContentReplacementState` in `tool_result_store.py`,
  which is also intentionally mutable.
- **REPL session-memory file path is `<workspace>/.simple-agent/
  session_memory.json`, not `~/.simple-agent/sessions/<name>.json`.**
  The plan's section 2 D2 task suggests a global `~/.simple-agent/
  sessions/` directory keyed by name; M3 only ships the auto-save
  primitive (B3), and the named multi-session storage is deferred
  to M4 (D2 explicitly handles that). Using a workspace-local path
  avoids polluting `$HOME` from tests and matches where
  `ProjectMemory` already lives via `memory_cli.py`.
- **`SessionMemory.load_json` is a classmethod returning a new
  instance**, not an instance method that loads into an existing
  store. This was the simpler shape for both the REPL wiring and
  the round-trip tests (`SessionMemory.load_json(path)` produces a
  fresh, populated `SessionMemory`). The plan did not pin a
  signature; the chosen one mirrors `MemoryEntry.from_dict`.

## 4. Open Questions / Blockers for M4

> Anything needing human input, or pre-conditions for M4.
> If none, write "(none)".

- (none) — all M3 gates green. The REPL `/stats` exit-gate is
  satisfied end-to-end via `python -m simple_coding_agent.cli --repl`
  with `/stats` printing the six counter lines. The
  `<workspace>/.simple-agent/session_memory.json` path that M3
  auto-uses is independent of (and will not collide with) the
  named-session storage M4 D2 introduces.

## 5. Next Session Prompt

> Paste the content of the fenced block below into a fresh `claude`
> session opened from `python-replica/`. The prompt is self-contained;
> the next session needs nothing from the current conversation.

```
I'm continuing work on simple_coding_agent, a Python replica of Claude
Code v2.1.88's context-management and memory pipeline.

Before doing anything:
1. Read CLAUDE.md (architecture + completed P-roadmap).
2. Read RUNTIME_ACTIVATION_PLAN.md
     - Section 4 for milestone M4's scope
     - Section 5 for execution rules
3. Read HANDOFF.md — pay close attention to Section 3
   "Decisions Made That Diverge From Plan".
4. Run `git log --oneline -10` and `pytest --tb=no -q` to confirm
   the baseline matches HANDOFF.md Section 1.

Then execute Milestone M4 only:
  - D1 + D2 + D3    (from RUNTIME_ACTIVATION_PLAN.md Section 2)

Follow Section 5 "Execution Rules" in RUNTIME_ACTIVATION_PLAN.md
strictly. The exact test case lists are in plan Section 3.4
(`test_transcript_persist.py` + `test_resume_session.py`) plus
the cross-session integration scenarios in 3.5.

Out of scope: any other milestone. Do NOT touch out-of-milestone code.

Exit ritual for this session (MANDATORY — do all five before stopping):
  1. Milestone M4's exit gate (per plan Section 4) is met
     — kill process mid-session, --resume restores summary.
  2. `git commit -m "P9-M4: <one-line>"` has landed.
  3. CLAUDE.md updated with a P9-M4 entry mirroring P1-P8 format.
  4. PROGRESS.md appended with a one-line summary
     (create the file if it does not exist yet).
  5. HANDOFF.md overwritten using templates/handoff_template.md, with
     all placeholders filled, to hand off to the M5 session.

Confirm you've read all three files (CLAUDE.md, RUNTIME_ACTIVATION_PLAN.md,
HANDOFF.md), then proceed directly to TDD.
```
