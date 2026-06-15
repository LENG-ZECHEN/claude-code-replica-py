# ADR-0005: Dream CLI subcommand, no-cron divergence, and dry-run-default safety posture

## Status

Accepted — M7 (session-memory-dream initiative), 2026-06-15

## Context

The TypeScript Claude Code source implements auto-dream as an
asynchronous, background-scheduled service with two trigger points:

1. **`utils/backgroundHousekeeping.ts:37` `initAutoDream`** — a
   startup arm that schedules periodic dream runs via the event loop.
2. **`query/stopHooks.ts:155` `executeAutoDream`** — a fire-and-forget
   call appended to every stop hook, so the dream fires at turn end
   when all gate checks pass.

The replica has no asyncio event loop and no cron daemon, so neither of
these surfaces can be mapped directly. M7 exposes two opt-in surfaces
instead:

- **`simple-agent memory dream`** — a CLI batch command (the
  externally-invoked analog of the scheduled dream).
- **`--dream-on-exit` REPL flag** — an opt-in post-session trigger
  (the in-loop analog of the stop-hook fire-and-forget, collapsed from
  per-turn to once-at-session-end because the replica is synchronous).

## Decisions

### 1. No cron / no background thread — CLI batch is the "scheduled dream"

**Decision**: The replica's "scheduled dream" = `simple-agent memory dream`
invoked by an external cron or RUNBOOK step. There is no background
housekeeping thread.

**Why**: The replica is synchronous. Introducing a background thread or
asyncio loop for a single mechanism would add significant complexity and
non-determinism to a codebase whose tests rely on full synchrony. The
CLI batch command achieves the same outcome with zero new concurrency
primitives.

**Consequence**: Operators who want periodic dream runs must wire an
external cron job (e.g. `0 2 * * * simple-agent memory dream --apply`).
This is documented in CLAUDE.md Current Limitations.

### 2. `--dream-on-exit` is opt-in, post-session only (not per-turn)

**Decision**: The REPL trigger fires exactly once at `/exit` or EOF, not
at every turn end like `executeAutoDream` in the TS stop hook chain.

**Why**: Per-turn dream consolidation in a synchronous REPL would block
the user between every turn. The replica already documents this divergence
pattern for session-memory updates (`maybe_update_session_memory` runs
once per stop hook, not per turn) and for sideQuery recall (synchronous
injection rather than async). The post-session single trigger is the
consistent and safe replica analog.

### 3. Dry-run is the default safety posture

**Decision**: `simple-agent memory dream` with no flags prints planned
`merged`/`pruned` counts and writes NOTHING. `--apply` is required to
actually consolidate.

**Why**: Dream is destructive — it deletes files via
`ProjectMemory.delete()`. Inverting the default would cause accidental
memory loss if a user runs `dream` without understanding its effect. The
dry-run default mirrors cautious CLI conventions (e.g. `rsync --dry-run`,
`terraform plan`).

The in-loop `--dream-on-exit` trigger is also OFF by default, mirroring
the `--extract-memories` and `--session-memory` opt-in patterns.

### 4. Dry-run uses a scratch-copy approach

**Decision**: `_dry_run_dream()` copies the real memory directory to a
`tempfile.TemporaryDirectory`, runs `DreamConsolidator.consolidate()` on
the copy with all gates trivially bypassed (`min_hours=0, min_sessions=0,
last_scan_at_ms=0`), and discards the temp directory. The returned
`DreamResult` shows planned counts without touching the real memory store.

**Why**: `DreamConsolidator` has no plan/preview API (M6 intentionally
kept it simple — one codepath). Adding a separate plan method would
duplicate the dedup algorithm. A scratch copy is O(N·file-size) but N is
small (≤200 entries) and each entry is a small Markdown file. The
TemporaryDirectory cleanup is guaranteed even on exception.

### 5. `recordConsolidation` is called inside `DreamConsolidator.consolidate()`

**Decision**: `record_consolidation(lock_path, now_ms)` (added to
`consolidation_lock.py` in M7) is called inside
`DreamConsolidator.consolidate()` after a successful run, so the time gate
re-opens after `MIN_HOURS` (24 h).

**Why**: Putting the stamp call inside `consolidate()` makes the method
self-contained: gate → run → stamp. This was explicitly deferred from M6
(HANDOFF noted "M7 must call `os.utime` or a helper after success"). The
alternative — requiring every caller to call `record_consolidation`
separately — would be error-prone and would split the lock invariant
across two callsites.

### 6. `--dream-on-exit` bypasses ALL gate thresholds (intentional)

**Decision**: When a REPL launched with `--dream-on-exit` reaches `/exit`,
EOF, or `max-turns` shutdown, `AgentLoop._run_dream_on_exit()` calls
`DreamConsolidator.consolidate()` with `min_hours=0.0, min_sessions=0,
last_scan_at_ms=0.0` — every gate in the M5 cascade trivially passes. A
fresh session of three turns will still trigger a consolidation on exit.

**Why**: The post-execution multi-agent review (2026-06-15) surfaced this
as an undocumented divergence from the PLAN's reading of "fires one dream
at REPL /exit", and the team accepted the bypass as the right semantic
for the in-loop trigger. Three reasons:

1. **Faithfulness vs UX trade-off.** The TS `executeAutoDream` in
   `query/stopHooks.ts:155` fires at every turn end and is gated by the
   normal cascade because per-turn frequency would otherwise destroy
   batteries. The replica's `--dream-on-exit` is once-per-session
   (collapsed from per-turn — see Decision 2 above), so the rate-limiting
   role the gates play in the TS source is already absorbed by the
   "one-shot at exit" reduction. Re-applying the same gate would
   double-rate-limit and most short sessions would consolidate zero
   times even though the user explicitly opted in.
2. **Opt-in already filters intent.** `--dream-on-exit` is OFF by default
   (mirroring `--extract-memories` and `--session-memory`). A user who
   sets it has actively asked for an exit-time consolidation; silently
   refusing because "you've only run 3 sessions today" violates the
   principle of least surprise for the opt-in surface.
3. **Operators who want gated periodic dream use the CLI batch.** The
   external-cron analog (`simple-agent memory dream --apply` per
   Decision 1) DOES honor the full cascade. The two surfaces are
   intentionally complementary: CLI = gated periodic; REPL flag =
   immediate per-exit.

**Consequence**: `_run_dream_on_exit()` is documented in the `loop.py`
docstring as "trigger irrespective of gate state — opt-in caller has
already declared intent". The CLI batch path remains the gated periodic
surface; do not pull the bypass into `simple-agent memory dream --apply`
without explicit owner approval. If a future user needs an exit-time
trigger that DOES respect the cascade (e.g. for headless harnesses that
launch many short sessions), the right addition is a separate
`--dream-on-exit-respect-gates` flag, not a flip of the default.

## Consequences

- `consolidation_lock.py` gains `record_consolidation` (exported in
  `__all__`).
- `dream.py::DreamConsolidator.consolidate()` gains one call to
  `record_consolidation` after the try block succeeds (minimal additive
  touch to a M6 module).
- No new cron daemon, no asyncio loop, no background thread.
- The no-cron divergence is documented in CLAUDE.md Current Limitations.
- `--dream-on-exit` is the only opt-in surface in the replica that
  intentionally bypasses the dream gate cascade; the CLI batch surface
  honors the full cascade and is the right tool for any usage pattern
  that needs throttling.
