---
slug: session-memory-dream
commit_prefix: sm-dream

milestones:

  M1:
    name: Generic ForkedAgentRunner (extract from ExtractMemoriesRunner)
    phase_ids: [F0]
    exit_gate: |
      New tests/test_forked_agent.py passes (≥ 6 cases) AND existing
      tests/test_extract_memories*.py stay green (pure refactor, behavior
      unchanged). `forked_agent.py::ForkedAgentRunner` exists with
      signature `run(task_prompt: str, context_messages: list[dict] = ())`
      and a per-call `can_use_tool(name, input) -> (allow: bool, reason)`
      gate. Assert: (a) context_messages ARE injected into the sub-agent's
      first provider call (MockProvider.history[0].messages contains them —
      fixes the current bug where base_messages is stored but never sent);
      (b) a tool the gate denies returns is_error=True with the gate's
      reason and NEVER reaches the ToolExecutor/registry; (c) max_turns is
      constructor-configurable and the for/else "max turns reached" error is
      preserved; (d) writes still confined to a fresh local store.
      ExtractMemoriesRunner is now a thin wrapper over ForkedAgentRunner
      (extract prompt + Edit-memory gate + max_turns=5). pytest total grows
      by ≥ 6 (from 912 baseline).
    notes: |
      Source mapping (read BEFORE implementing):
        - claude-code-source-code/src/utils/forkedAgent.ts:489 runForkedAgent
        - claude-code-source-code/src/utils/forkedAgent.ts:345 createSubagentContext
        - claude-code-source-code/src/services/extractMemories/extractMemories.ts:171
          createAutoMemCanUseTool — the canonical per-call allow/deny gate
        - claude-code-source-code/src/services/SessionMemory/sessionMemory.ts:460
          createMemoryFileCanUseTool — the narrow "Edit one file only" gate

      This is a PURE refactor that unlocks M2–M7. The replica ALREADY has
      forked-agent capability embodied in extract_memories.py
      (ExtractMemoriesRunner: isolated multi-turn loop, own provider/
      system/tools, whitelisted executor, MAX_TURNS=5, fresh
      ProjectMemory writes). We are generalizing it, not building new.

      Two things to fix/add while generalizing:
        1. CONTEXT INJECTION GAP (real bug): extract_memories.py:118 stores
           self._base_messages but run() (:126) builds messages from ONLY
           the task prompt — the conversation is never sent. ForkedAgentRunner
           MUST accept context_messages and prepend them. (Dream passes none;
           it reads from disk via tools. SM-extraction passes the post-
           last-summarized message slice.)
        2. PER-CALL GATE replaces the name-whitelist: lift the current
           _TOOL_WHITELIST check into a `can_use_tool` callback so callers can
           express path-scoped rules (read-only ops + writes within a dir).
           This is the SAME philosophy as plan-mode soft-deny in
           loop.py::_execute_one (read_only flag → is_error, no schema filter).

      Scope / explicitly NOT doing (OpenAI-compatible target, document in
      forked_agent.py header):
        - NO prompt-cache machinery (Anthropic CacheSafeParams /
          forkContextMessages cache-key preservation). OpenAI/DashScope
          caching is implicit/prefix-based — no fork-cache option exists
          (see CLAUDE.md provider notes). LLM mode = a normal Provider.call
          loop; reusing the same prefix may get automatic cache benefit but
          we neither set nor depend on it.
        - NO OS-level sandbox / separate process — "isolation" = own message
          list + restricted gate + writes confined to a dir + bounded turns.

  M2:
    name: SessionMemoryState + incremental fold + SessionMemorySummarizer
    phase_ids: [S1]
    exit_gate: |
      tests/test_session_memory_state.py AND
      tests/test_session_memory_summarizer.py pass. `SessionMemoryState`
      (new session_memory_state.py) holds the running 9-section summary;
      `to_jsonable()/from_jsonable()` round-trip including unknown-key
      forward-compat; `update_session_memory(state, new_messages)` returns a
      NEW state (input unchanged — immutability) folding messages into the
      fixed sections. `SessionMemorySummarizer(state, fallback)` implements
      the Summarizer Protocol: on a WARM state, `.summarize(msgs)` returns the
      prewarmed text and makes ZERO provider calls (assert MockProvider.history
      empty); on a COLD/empty state it delegates to the configured fallback
      (RuleBasedSummarizer or LLMSummarizer). `ContextCompactor(
      summarizer=SessionMemorySummarizer(prewarmed))` produces a valid
      CompactSummary with non-empty summary_text. pytest grows by ≥ 12.
    notes: |
      Source mapping:
        - sessionMemoryCompact.ts:58-60 DEFAULT_SM_COMPACT_CONFIG
          (minTokens=10_000, minTextBlockMessages=5, maxTokens=40_000)
        - SessionMemory/prompts.ts:11-41 DEFAULT_SESSION_MEMORY_TEMPLATE
          (the fixed markdown sections: Session Title / Current State /
          Task specification / Files and Functions / Workflow /
          Errors & Corrections / Documentation / Learnings / Key results /
          Worklog) — header + italic instruction lines are load-bearing
        - SessionMemory/prompts.ts:256 truncateSessionMemoryForCompact
          (per-section cap MAX_SECTION_LENGTH=2000 tok; total 12_000)

      Design: the 9-section accumulator mirrors RuleBasedSummarizer's
      existing section extraction (reuse those heuristics for the
      deterministic fold). DEFAULT engine is LLM (M3 wires the LLM updater);
      the deterministic fold here is the no-API/test fallback AND the thing
      SessionMemorySummarizer reads at compaction.

      Scope: this milestone is ABSTRACTION + UNIT TESTS only. NO loop
      wiring, NO session_store, NO CLI (those are M3). Keep
      ContextCompactor / CompactSummary / Summarizer Protocol unchanged
      (drop-in summarizer).

  M3:
    name: Wire session-memory into loop + LLM updater + cross-process persistence
    phase_ids: [S2, S3]
    exit_gate: |
      Behind a `--session-memory` flag (default OFF, mirrors
      extract_memories_enabled): `maybe_update_session_memory(...)` runs in
      loop.py::_run_stop_hooks and keeps SessionMemoryState warm across REPL
      turns. At compaction, loop.py::_force_compact uses
      SessionMemorySummarizer so a WARM reuse makes ZERO summarization
      provider calls — assert via MockProvider call-count delta across a
      budget-driven compaction (full path would add ≥1 call; SM reuse adds
      0). The LLM-mode updater uses ForkedAgentRunner (from M1) with an
      Edit-summary.md-only can_use_tool gate. session_store.py round-trips
      `session_memory_state` (save_session/load_session; absent key → empty
      state, backward compatible with old session files). Extend
      tests/test_end_to_end_long_session.py: cross-process resume preserves
      the warm SM so session B's first compaction reuses it. Two-tier
      fallback holds: cold/empty SM → full Rule/LLM compaction (null-vs-throw
      contract, no crash). pytest grows by ≥ 10.
    notes: |
      Source mapping:
        - autoCompact.ts:241 autoCompactIfNeeded — tries SM compaction
          FIRST (:288), only null falls through to full compactConversation
          (:312). Replicate the two-tier "try cheap, fall back to full".
        - sessionMemoryCompact.ts:498 — "SM-compact has no compact-API-call"
          (the confirmed basis for the time saving)
        - SessionMemory/sessionMemory.ts:488 updateLastSummarizedMessageIdIfSafe
          — only advance the keep-boundary when the last turn has NO tool
          calls (don't orphan tool_results across the cut)
        - compact.ts:1136 streamCompactSummary — the LLM call we SKIP

      Replica integration points: loop.py::_run_stop_hooks:578 (add the
      synchronous incremental update beside maybe_extract_memories),
      loop.py::_force_compact:690 (inject SessionMemorySummarizer when
      --session-memory is on), session_store.py::_summary_to_dict /
      _summary_from_dict / save_session / load_session.

      DIVERGENCE TO DOCUMENT (Current Limitations + module header): replica
      has no asyncio loop, so TS's fire-and-forget background extraction
      (query.ts:1001 `void executePostSamplingHooks`) becomes a SYNCHRONOUS
      incremental fold at the stop hook. Net effect is the same — the
      summarization cost is amortized across turns so compaction-time reuse
      is ~O(0) — but the producer is not a separate thread. State this the
      same way the loop already documents synchronous sideQuery recall.
      (Optional, NOT required this M: a thread-backed truly-concurrent
      updater — leave a note, don't build it.)

  M4:
    name: SM-compact observability + dual-arm latency benchmark
    phase_ids: [S4]
    exit_gate: |
      MetricsCollector gains `sm_compact_reuses` and `sm_compact_misses`
      (record_* methods + format_stats lines) surfaced via the REPL /stats
      command. The reuse/miss signal is emitted on the EXISTING 'compact'
      trace channel as a `reused=<bool>` field (NO new channel — the 11-name
      vocab is frozen and test-pinned; assert the StderrTracer line).
      New benchmarks/bench_sm_compact_latency.py runs headless and writes
      benchmarks/_results/04_sm_compact_latency.{json,md} with TWO clearly
      labeled arms: (a) DETERMINISTIC — RuleBasedSummarizer real recompute
      vs O(0) SessionMemorySummarizer reuse, no API, fully reproducible
      (the defensible floor); (b) REAL-API (gated behind --confirm-api-call
      + key, like bench_openai_cost.py) — measured LLMSummarizer wall-clock
      vs ~0 reuse on DashScope qwen-plus-latest. JSON includes raw per-run
      perf_counter timings (median + p90 over R≥50) and a `latency_source`
      field disclosing where each number came from. tests/test_bench_sm_compact.py
      asserts measured_reuse_ms < full_arm_ms with a tiny injected delay so
      CI stays fast. pytest grows by ≥ 7.
    notes: |
      Honesty rules (this benchmark EXISTS to replace the never-existed
      "98.7%" claim — do not reintroduce a fabricated percentage):
        - Every number discloses its source. Deterministic arm = reproducible
          floor; real-API arm = realistic headline; both labeled, never
          conflated.
        - Report it as "full summarize measured Xs (DashScope) → SM reuse
          ~0ms (median of N)", with the real arm flagged "live API, drifts
          run-to-run" exactly like bench3.
      Template: benchmarks/bench_compression_ratio.py (deterministic, no-net,
      writes _results/NN_*). Real-API precedent: benchmarks/bench_openai_cost.py
      (DashScope, --confirm-api-call + key gate, exit 2/3, _MODEL_PRICES).

  M5:
    name: consolidation_lock + faithful dream gate cascade
    phase_ids: [D1]
    exit_gate: |
      New src/simple_coding_agent/consolidation_lock.py replicates the
      cheapest-first dream gate cascade with these functions (mirroring the
      TS names): read_last_consolidated_at(), list_sessions_touched_since(),
      try_acquire_consolidation_lock(), rollback_consolidation_lock(), and a
      single should_dream(...) (or gate-cascade) entry that runs them in
      order. The lock file `.consolidate-lock` is BOTH the PID mutex (body =
      PID, 1h staleness via HOLDER_STALE_MS) AND the timing state (its mtime
      == lastConsolidatedAt — no separate state file). Gate cascade: time
      gate (≥ 24h since lock mtime), 10-min scan throttle, session gate
      (≥ 5 sessions touched since lastConsolidatedAt, current session
      excluded). rollback rewrites mtime so the time gate re-opens after a
      failure. tests/test_consolidation_lock.py passes (≥ 8 cases:
      time-gate open/closed, session-gate count incl. current-session
      exclusion, scan-throttle, acquire returns prior mtime / None when
      held, rollback rewinds, mtime==lastConsolidatedAt round-trip). All
      timestamps are injected (no real sleep); use os.utime + monkeypatch.
      pytest grows by ≥ 8.
    notes: |
      Source mapping:
        - autoDream/autoDream.ts:63-66 DEFAULTS (minHours=24, minSessions=5);
          :56 SESSION_SCAN_INTERVAL_MS=10min; :95 isGateOpen; :125 runAutoDream
          gate order (cheapest first: enabled → time → scan-throttle →
          session → lock)
        - autoDream/consolidationLock.ts: readLastConsolidatedAt:29,
          tryAcquireConsolidationLock:46, rollbackConsolidationLock:91,
          listSessionsTouchedSince:118, HOLDER_STALE_MS=1h, LOCK_FILE
          '.consolidate-lock'

      This milestone is the LOCK + GATING infrastructure ONLY — no
      DreamConsolidator engine yet (that is M6). Keep it pure and heavily
      unit-tested; M6 depends on it. Replica divergence: "sessions touched
      since" counts session files under the replica's sessions dir
      (resolve_sessions_dir / SIMPLE_AGENT_SESSIONS_DIR), since the replica
      has its own session_store layout — document this mapping.

  M6:
    name: DreamConsolidator engine (4-stage forked agent + deterministic fallback)
    phase_ids: [D2]
    exit_gate: |
      New src/simple_coding_agent/dream.py::DreamConsolidator. LLM mode runs
      ForkedAgentRunner (M1) with the ported 4-stage consolidation prompt
      (Orient / Gather / Consolidate / Prune+Index) and a memory-dir-scoped
      can_use_tool gate (read-only list/read/search + writes confined to
      memory_dir; max_turns ≈ 20). Deterministic fallback (MockProvider /
      no provider) does Jaccard dedup of near-identical entries (keep newest,
      conservative high threshold) + mtime-based prune. Returns frozen
      `DreamResult(merged, pruned, runs, written_paths)`. All writes go
      through ProjectMemory.save/delete (secret + path-traversal guards
      intact). Idempotent: a second dream over an already-consolidated store
      is a no-op (merged=0, pruned=0). Gating reuses M5's consolidation_lock.
      tests/test_dream_consolidator.py passes (≥ 10 cases incl. the
      deterministic dedup/prune/idempotency paths under MockProvider).
      pytest grows by ≥ 10.
    notes: |
      Source mapping:
        - autoDream/consolidationPrompt.ts:10 buildConsolidationPrompt —
          PORT the 4 phases AND the anti-turn-waste directives verbatim in
          spirit: "grep narrowly, don't read whole files", "Look only for
          things you already suspect matter", and feed the session-id list
          into the prompt so the agent doesn't scan to find scope.
        - extractMemories/extractMemories.ts:171 createAutoMemCanUseTool —
          the memory-dir gate to mirror (read-only ops + writes within dir)
        - memdir.ts MAX_ENTRYPOINT_LINES=200 / MAX_ENTRYPOINT_BYTES=25_000
          (the MEMORY.md prune targets)

      Dream is the periodic-CONSOLIDATION counterpart to per-turn
      extract_memories (capture). DEFAULT engine = LLM (the forked agent
      runs the prompt and does the merge itself — the harness does NOT
      merge); deterministic Jaccard/mtime path is the no-API/test fallback.
      DEPENDS ON: M1 (ForkedAgentRunner) for the LLM path, M5
      (consolidation_lock) for gating. Reuse MemorySelector for dedup
      scoring.

  M7:
    name: dream CLI subcommand + optional post-session trigger + metrics + docs
    phase_ids: [D3, D4]
    exit_gate: |
      memory_cli gains a `dream` subcommand: DEFAULT dry-run (prints planned
      merged/pruned counts, writes NOTHING), `--apply` actually consolidates,
      `--force` bypasses the M5 gate cascade for demo. Resolves memory_dir
      from SIMPLE_AGENT_MEMORY_DIR or <cwd>/.simple-agent/memory/; exit 0 on
      success, exit 2 on bad dir; MockProvider default, `--provider openai`
      constructs an OpenAIProvider (mocked in tests). Optional in-loop
      trigger behind `--dream-on-exit` (default OFF, mirrors
      extract_memories_enabled) fires one dream at REPL /exit. MetricsCollector
      gains dream_runs / dream_merged / dream_pruned shown in /stats. An ADR
      under docs/DECISIONS, CLAUDE.md per-file summaries, and Current
      Limitations (the no-cron divergence) are updated.
      tests/test_memory_cli_dream.py passes. pytest grows by ≥ 8.
    notes: |
      Source mapping:
        - query/stopHooks.ts:155 executeAutoDream (fire-and-forget at turn
          end) — replica analog = the opt-in /exit trigger + the CLI batch
          command
        - utils/backgroundHousekeeping.ts:37 initAutoDream (startup arm)

      DIVERGENCE TO DOCUMENT PROMINENTLY: replica has no cron, so "scheduled
      dream" = `simple-agent memory dream` invoked by an EXTERNAL cron /
      RUNBOOK; the in-loop trigger is opt-in, post-session only (not
      per-turn). Safety: dry-run default protects against memory data loss;
      --apply required to write.

      memory_cli precedent to extend: existing add/list/delete/search/show
      arg routing, SIMPLE_AGENT_MEMORY_DIR resolution, exit-code-2 convention,
      and cli._build_repl_loop's provider-injection (Mock vs OpenAI) pattern.
---
> Bootstrapped on 2026-06-15. Baseline commit: 094cf90d09fef37b3f8357b4e2b8de0434834dfd. Baseline pytest: 912 passing (+1 xpassed).
> STATUS: complete (M1–M7 shipped on 2026-06-15)

# Goal

Build the two unbuilt mechanisms that complete the replica's
context/memory fidelity to Claude Code v2.1.88: **(A) session-memory
compaction** — make auto-compaction cheap by reusing an
incrementally-maintained session summary so the compaction-time LLM
summarization call is skipped — and **(B) auto-dream** — a periodic,
gated, forked sub-agent that consolidates (merges / dedups / prunes /
re-indexes) the cross-session memory store. Both are built on one new
generic `ForkedAgentRunner` (M1). Outcome: the agent's auto-compaction
becomes near-instant at the trigger moment (proven by a disclosed,
reproducible wall-clock benchmark that replaces the never-existed
"98.7%" figure), and the memory subsystem gains its missing 4th layer
(periodic consolidation), the counterpart to today's per-turn
extract_memories capture.

# Background / motivation

A résumé fact-check (2026-06) confirmed two claims had no backing code:
the "background session-memory saves 98.7% of compaction time" figure
appears nowhere, and "auto-dream" was only a deferred TODO. Both are
REAL Claude Code features with full TS source to map against
(src/services/compact/sessionMemoryCompact.ts,
src/services/SessionMemory/*, src/services/autoDream/*). This initiative
makes the claims true and defensible, with a benchmark that reports only
disclosed, reproducible numbers.

# Design sketch

- **M1 ForkedAgentRunner** (forked_agent.py): generalize the existing
  ExtractMemoriesRunner into a reusable multi-turn sub-agent —
  `run(task_prompt, context_messages=())` + a per-call
  `can_use_tool(name, input)` gate (path-scoped; same philosophy as
  plan-mode soft-deny) + configurable `max_turns`. ExtractMemoriesRunner
  becomes a thin wrapper. Fixes the real bug where base_messages is
  stored but never sent to the sub-agent.
- **Producer/consumer split for SM** (M2–M4): `SessionMemoryState` +
  `update_session_memory` (incremental 9-section fold, synchronous at the
  stop hook = the no-async stand-in for TS background extraction) feed a
  `SessionMemorySummarizer` that returns the warm summary at O(0)
  compaction cost, falling back to Rule/LLM when cold. Persisted in
  session_store so cross-process resume stays warm. Observability +
  dual-arm latency benchmark prove the saving honestly.
- **Dream** (M5–M7): `consolidation_lock` (M5) replicates the faithful
  cascade (24h / ≥5 sessions / 10-min scan throttle / PID mutex whose
  mtime is lastConsolidatedAt); `DreamConsolidator` (M6) runs the ported
  4-stage prompt via ForkedAgentRunner (default LLM; deterministic
  Jaccard/mtime fallback). Exposed (M7) as `simple-agent memory dream`
  (dry-run/--apply/--force) — the no-cron stand-in for the TS stop-hook
  schedule — plus an opt-in /exit trigger.

# Risks / known unknowns

- **Benchmark honesty** (highest risk — it's the whole point): never
  reintroduce a fabricated %; every number discloses source; ship the
  deterministic floor AND the real-API arm, labeled.
- **No async / no cron**: TS background extraction → synchronous
  stop-hook fold; TS scheduled dream → CLI subcommand. Document both as
  intentional divergences (precedent: synchronous sideQuery recall).
- **Dream is destructive** (merges/prunes/deletes memory files):
  dry-run default, --apply to write, conservative dedup threshold, all
  writes via ProjectMemory guards, OFF by default in the loop.
- **session_store back-compat**: new keys must be optional (absent →
  empty), mirroring how restored_files/timestamp are already optional.
- **Frozen 11-channel trace vocab**: reuse 'compact' for SM; surface
  dream via metrics + CLI, NOT a new trace channel.

# Out of scope (this initiative)

- Anthropic prompt-cache machinery (CacheSafeParams / cache-key
  preservation) — no OpenAI-compatible equivalent; LLM mode is a plain
  Provider.call loop.
- A truly-concurrent thread-backed background extractor (synchronous
  incremental fold is sufficient and testable; leave a note).
- The TS TUI dream surfacing (DreamTask registry, footer pill,
  DreamDetailDialog), KAIROS /dream skill, team-memory, remote-memory-dir,
  agentMemorySnapshot — all UX/feature-flag layers with no effect on
  memory content.
- GrowthBook flag plumbing (use local flags/env + the documented defaults).

# Anything else

Locked design decisions (owner-confirmed 2026-06-15):
1. **One generic ForkedAgentRunner** (M1) backs both SM-extraction (LLM
   mode) and dream. Confirmed.
2. **Engine fidelity: default LLM mode + deterministic fallback** for
   both SM-extraction and dream — mirrors the existing
   LLMSummarizer/RuleBasedSummarizer split (provider present → LLM, else
   deterministic).
3. **Benchmark: dual-arm** (real DashScope LLM latency headline +
   deterministic recompute-vs-reuse reproducible floor). Replaces the
   never-existed 98.7%.
4. **Dream gating: faithfully replicate the cascade** (mtime lock =
   lastConsolidatedAt, 24h time gate, ≥5-session gate, 10-min scan
   throttle, PID mutex), with `--force` to bypass for demo.
5. **Isolation = path-scoped can_use_tool gate** (read-only ops + writes
   confined to a dir), same philosophy as plan-mode soft-deny — NOT just
   a tool-name whitelist.

Provenance / numbering note (Phase 1, 2026-06-15): the owner-approved M4
split landed as **M5 (lock + gate cascade) + M6 (consolidator engine)**,
and the old "dream CLI" milestone became **M7**, because
`run_all_milestones.sh` only recognizes pure-numeric milestone IDs
(`list_milestones_from_config` matches `M[0-9]+:`; the append-only check
extracts `M[0-9]+`). Letter-suffix IDs (M4a/M4b) would be silently
skipped by Phase 2, so the split was renumbered into the M1–M7 sequence.

Dependency order: M1 must land first (M2–M7 depend on ForkedAgentRunner).
S-line (M2→M3→M4) and D-line (M5→M6→M7) are otherwise independent; M6
depends on both M1 (runner) and M5 (lock). The linear M1→…→M7 order is
safe.

> SIZING NOTE: M3 (wiring) is the heaviest remaining single milestone but
> stays under thresholds (≤4 components, ~10 tests, "wire" not
> "introduce+wire+CLI"). The original M4 (dream engine + lock) was split
> into M5/M6 per owner approval. M1/M2/M4/M5/M7 are believed atomic.

> Current pytest baseline at brief time: 912 passing (+1 xpassed),
> mypy --strict + ruff clean. Every milestone must keep mypy + ruff clean.
