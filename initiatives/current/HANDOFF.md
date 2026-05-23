# HANDOFF — Next: M3 (autocompact-recent-files-attachment)

> Updated by: M2 (engine-snip-orphan-and-ancient-pairs)
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-pdf-align`
- **current milestone**: `M2` — DONE
- **next milestone**: `M3` — autocompact-recent-files-attachment
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [next], M4 [pending]

## 2. Completed milestones

### M1

- **commit**: `[ctx-pdf/M1] compact-thresholds-and-llm-default` (SHA in `git log`)
- **files changed**: `src/simple_coding_agent/compact.py`,
  `src/simple_coding_agent/cli.py`, `tests/test_compact.py`,
  `tests/test_repl.py`, `tests/test_loop.py`,
  `tests/test_metrics_collector.py`, `tests/test_microcompact_runtime.py`,
  `examples/microcompact_demo.py`
- **tests added**: `tests/test_compact.py` (+14 cases), `tests/test_repl.py`
  (+3 cases). Total: 615 → 632 (+17).
- **behavior implemented**: Three additive PDF-alignment deltas in
  `compact.py`. (a) `MicroCompactor` gained a keyword-only
  `keep_recent: int = 5`; `microcompact()` now preserves the 5 most
  recent compactable tool_results (global transcript order) and clears
  only older ones (`_recent_compactable_positions` computes the
  preserve set). `keep_recent=0` reproduces the pre-PDF clear-everything
  behaviour; `keep_recent < 0` raises `ValueError`. (b)
  `ContextCompactor.should_compact()` now fires when EITHER the new PDF
  formula (`used >= budget.max_tokens - output_headroom(12_000)
  - compact_headroom(20_000)` AND `used >= min_session_tokens(30_000)`)
  OR the legacy ratio (`used > available_tokens * compact_threshold`)
  fires. The three new knobs are keyword-only constructor params with
  PDF defaults. (c) `ContextCompactor` gained a keyword-only
  `provider: Provider | None = None`; when no explicit `summarizer` is
  given, a supplied provider selects `LLMSummarizer`, else
  `RuleBasedSummarizer` (backward compat). An explicit `summarizer`
  always wins. `cli.py` added 4 flags
  (`--microcompact-keep-recent`, `--output-headroom`,
  `--compact-headroom`, `--min-session-tokens`) threaded through
  `_resolve_threshold` into both REPL compactor-wiring branches.
- **design decisions (deviations from PLAN)**:
  - `keep_recent=5 default ripples into runtime`: the exit gate mandates
    `keep_recent: int = 5`, and `AgentLoop` builds its default
    `MicroCompactor()` (loop.py:180), so single-result clearing now
    preserves rather than clears. Four pre-PDF assertions that relied on
    the old clear-everything default were updated to construct the
    microcompactor with `keep_recent=0` — exactly the construction the
    exit-gate parenthetical names ("pre-PDF default-behaviour test still
    passes when explicitly constructed with keep_recent=0"). Sites:
    `tests/test_loop.py::test_agent_loop_microcompacts_old_tool_results_before_context_building`,
    `tests/test_metrics_collector.py::test_metrics_counts_microcompact_invocations`,
    `tests/test_microcompact_runtime.py::test_microcompact_fires_when_assistant_older_than_60min`,
    and `examples/microcompact_demo.py::_CallCountingMicroCompactor`.
    Three microcompact tests in `tests/test_compact.py` were likewise
    switched to `keep_recent=0`. This overrides the prompt §4 blanket
    "every existing test ... without modification" wording, which the
    exit-gate parenthetical and §3 ("git diff + test output is source of
    truth") supersede. Impact on next milestone: none — M2 touches snip,
    not microcompact.
  - `CLI flags use preset_key=None`: the 4 new flags resolve through
    `_resolve_threshold` with NO `_AGGRESSIVE_THRESHOLDS` entry (the
    `--max-steps` pattern), so the frozen preset dict was left untouched
    (`examples/visibility_full_demo.py` imports it; the precedence-matrix
    test iterates the 8 original keys). Explicit flag > built-in default;
    the aggressive preset does not override these fields. Visible in:
    `cli.py:_build_repl_loop`. Impact on next milestone: none.
- **known limitations**:
  - In aggressive mode the new microcompact default `keep_recent=5`
    applies (no preset override), so an aggressive demo with ≤5
    compactable results clears nothing via microcompact. No demo test
    asserts microcompact clear counts, so all stay green; a future
    milestone could add a `microcompact_keep_recent` preset entry if an
    aggressive demo needs clear-everything behaviour.
  - No production call site passes `provider=` to `ContextCompactor`
    yet — M1 only added the surface, as scoped. The LLM-summarizer
    default is exercised only in tests.

### M2

- **commit**: `[ctx-pdf/M2] engine-snip-orphan-and-ancient-pairs` (SHA in `git log`)
- **files changed**: `src/simple_coding_agent/snip.py`,
  `src/simple_coding_agent/models.py`,
  `src/simple_coding_agent/context.py`, `tests/test_snip.py`
- **tests added**: `tests/test_snip.py` (+15 cases). Total: 632 → 647 (+15).
- **behavior implemented**: Engine `SnipTool.snip()` expanded from a
  pure fold into a 4-phase pipeline. Phase 1 (existing) folds redundant
  fresh results — untouched. Phase 2 (new) DELETES orphan `tool_use`
  blocks (no matching `tool_result`) and orphan `tool_result` blocks
  (no matching `tool_use`), both directions, unconditionally, for ALL
  tools (this is API-validity GC, not P8 folding). Phase 3 (new)
  DELETES paired `(tool_use, tool_result)` blocks whose result content
  == `CLEARED_TOOL_RESULT_CONTENT`, oldest-first, gated on the summed
  estimated tokens of all cleared placeholders reaching
  `ancient_cleared_threshold_tokens` (keyword-only ctor param, default
  10_000); eviction subtracts each evicted message's estimate and stops
  as soon as the running total drops below threshold (so threshold=N
  evicts down to just under N, not necessarily everything). Phase 4
  (new) inserts exactly one `SNIP_BOUNDARY` marker at the position of
  the earliest deleted block whenever any deletion happened. New
  `MessageType.SNIP_BOUNDARY` + `Message.snip_boundary()` (SYSTEM role,
  `is_meta=True`, mirrors `compact_boundary()`), filtered alongside
  `COMPACT_BOUNDARY`/`ATTACHMENT` in `context._normalize_messages()`.
  `should_snip()` gained a 4th True branch ("cleared tokens >=
  threshold") beside path-count>=3 and pair-count>=10. Token estimate
  per message via new module helper `_estimate_message_tokens()`
  (serializes role+content blocks in the `_normalize_messages` shape,
  then `ContextBudget.estimate_tokens`); `_cleared_token_total()` and
  `_cleared_messages()` expose the sum / per-message ordering.
- **design decisions / deviations from PLAN**:
  - `orphan deletion is opportunistic, not threshold-gated`: orphans
    are deleted whenever `snip()` runs, independent of any threshold.
    But `snip()` only runs when `should_snip()` is True, and the exit
    gate only added a should_snip branch for cleared-tokens — NOT for
    orphans. So a transcript whose ONLY anomaly is orphans (no
    fold-trigger, no cleared-token-trigger) will not invoke engine snip
    at the loop call site; `context._remove_orphan_tool_results()`
    remains the build-time backstop that catches those. This matches
    the PLAN risk note "snip must run before build()'s orphan pass" and
    the invariant that `_remove_orphan_tool_results()` stays live.
  - `"text AND tool_use" edge handled structurally`: the `Message`
    content type is `str | list[ToolCall|ToolResult]`, so a single
    message cannot hold both a text string and tool_use blocks. A plain
    assistant text message (string content) is never a deletion carrier
    — it survives untouched when an adjacent orphan tool_use message is
    dropped. Within a list-content message, only targeted blocks are
    removed; the message is dropped only when its block list empties.
    Covered by `test_snip_drops_one_orphan_block_keeps_sibling_in_same_message`
    and `test_snip_keeps_adjacent_text_message_when_tool_use_deleted`.
  - `engine snip call site unchanged`: `loop.py:215 _maybe_snip()`
    position stays, per the user's confirmation. `_maybe_snip` already
    runs on `self._transcript.all_messages()` and `replace_all`s the
    result, so the inserted `SNIP_BOUNDARY` lands in the live transcript
    with no loop change. M2 touched no loop / cli code.
- **known limitations**:
  - The cleared-token sum is computed at MESSAGE granularity (a message
    with >=1 cleared result contributes its whole estimated tokens
    once). With the standard one-result-per-message transcript shape
    this equals per-pair granularity. A message bundling multiple
    cleared results would be evicted/counted as a unit. No current
    producer emits such bundles (microcompact clears in place, one
    result per user message).
  - Orphan deletion intentionally applies to side-effecting tools
    (`write_file`/`edit`) too — but only to DANGLING blocks, never to
    folding their content. The P8 "don't fold side-effecting results"
    invariant is unaffected.

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `[ctx-pdf/M2] ...` (run `git -C python-replica log --oneline -3`)
- **tests**: 647 passing
- **mypy**: clean (21 source files)
- **ruff**: clean
- **branch**: main
- **known failing checks**: none

## 4. Important constraints (carried forward)

> Invariants that all subsequent milestones MUST respect. Each milestone
> can ADD entries here; entries are removed only when explicitly retired.

- **do not modify**: `src/simple_coding_agent/tool_result_store.py`
  (mechanism 1 / tool_result_budget is already 1:1 with the PDF
  reference, including prompt-cache stability via
  `ContentReplacementState`; no milestone of this initiative touches
  this file).
- **preserve**: every existing test in `tests/test_snip.py` MUST
  continue passing without modification (M2 extends behaviour
  additively).
- **compatibility requirements**:
  - `ContextCompactor`'s legacy `compact_threshold` ratio is now the
    SECOND trigger inside `should_compact()` (OR'd with the PDF
    double-headroom formula). **Do NOT remove this legacy second-trigger
    path in any later milestone** — the aggressive-thresholds preset and
    the `examples/visibility_full_demo.py` / `examples/stress_demo.py`
    demos rely on lowering `compact_threshold` to fire compaction in
    tiny budgets where the 30k `min_session_tokens` floor blocks the
    new formula.
  - `MicroCompactor.keep_recent` defaults to 5 (PDF "keep latest 5").
    Tests that need the pre-PDF clear-everything behaviour MUST
    construct `MicroCompactor(keep_recent=0)`; do not "fix" them by
    reverting the default.
  - `_remove_orphan_tool_results()` in `context.py` stays in place
    as defence-in-depth even after M2 makes snip the primary orphan
    handler.
  - **(added by M2)** `MessageType.SNIP_BOUNDARY` MUST be filtered
    alongside `COMPACT_BOUNDARY` in every API-serialization site. Today
    that site is `context._normalize_messages()`. M3 and M4 must NOT
    introduce a new serialization path that skips this filter. (It is
    naturally inert in `RuleBasedSummarizer.summarize` because it is a
    SYSTEM-role message with string content, which falls through every
    summarizer branch — but any future summarizer that inspects SYSTEM
    messages must skip it like COMPACT_BOUNDARY/ATTACHMENT.)
  - **(added by M2)** `_remove_orphan_tool_results()` remains the live
    build-time backstop. Engine snip handles orphans only when it runs
    (gated by `should_snip`), so the build pass is NOT redundant — do
    NOT remove it in M3 or M4.
  - **(added by M2)** `SnipTool.snip()` must remain idempotent: a second
    application to an already-snipped transcript inserts no second
    SNIP_BOUNDARY and deletes nothing further. Deletion phases must
    never create new orphans (orphan-result delete leaves no use to
    re-orphan; pair delete removes both halves). Preserve this if snip
    phases are extended.

## 5. Next milestone guidance

For `M3` — autocompact-recent-files-attachment:

- **next scope** (paraphrased from PLAN; config.yaml is authoritative):
  snapshot recent `read_file` contents BEFORE compaction and re-inject
  them into the rebuilt context as ATTACHMENT messages — do NOT have the
  model re-read. Three pieces: (1) `AgentLoop` carries
  `_recent_file_snapshots: deque[FileSnapshot]` (cap N, default 5),
  populated inside `_execute_one()` on a successful `read_file` call;
  `FileSnapshot` = frozen dataclass `path: str`, `content: str`,
  `captured_at: str`. (2) `_force_compact()` passes the deque into
  `ContextCompactor.compact(snapshots=...)`, which stores it on the
  returned `CompactSummary.recent_file_snapshots: tuple` (CompactSummary
  becomes frozen, new field defaults to `()`). (3) `ContextBuilder.build()`
  reads `compact_summary.recent_file_snapshots` and emits one
  `MessageType.ATTACHMENT` user-role message per snapshot, immediately
  after COMPACT_BOUNDARY and before the keep_recent messages, content
  `<recent-files>\n<file path="...">CONTENT</file>\n</recent-files>`,
  `is_meta=True`, NOT counted toward keep_recent trimming. Exit gate:
  pytest +>=8 from baseline.
- **relevant files**: `loop.py` (snapshot capture hook in `_execute_one`
  after read_file success; pass deque into `_force_compact`),
  `compact.py` (`CompactSummary` → frozen + new field;
  `ContextCompactor.compact(snapshots=...)`), `context.py`
  (`ContextBuilder.build` emits ATTACHMENT messages from the summary),
  `models.py` (verify `MessageType.ATTACHMENT` already exists — it does,
  at the enum; `FileSnapshot` likely lives in models or compact).
- **CONFIRMED for M3**: `MessageType.ATTACHMENT` already exists in the
  enum (models.py). **But** `context._normalize_messages()` currently
  FILTERS ATTACHMENT out alongside COMPACT_BOUNDARY/SNIP_BOUNDARY (M2
  left that filter as-is, since attachments are unused today). M3 MUST
  change that filter so ATTACHMENT messages PASS THROUGH to API
  serialization (they are real user-role content the model must see),
  while keeping COMPACT_BOUNDARY and SNIP_BOUNDARY filtered. This is the
  single biggest gotcha for M3 — the PLAN risk note flagged it and M2
  confirms it: ATTACHMENT is in the drop tuple right now.
- **interaction with M2's snip phase that M3 should know**: engine snip
  runs (`loop.py:215`) BEFORE `_maybe_compact()` (loop.py:216), so any
  SNIP_BOUNDARY is already in the transcript when compaction slices at
  the COMPACT_BOUNDARY. `messages_after_compact_boundary()` returns
  everything after the latest compact boundary, which can include a
  SNIP_BOUNDARY — harmless, it is filtered at normalize. M3's ATTACHMENT
  injection happens in `build()` AFTER the post-compact slice, so it
  does not interact with snip. Also: the build-time
  `_remove_orphan_tool_results()` runs after the trim loop; ATTACHMENT
  messages are user-role with string content, so they are not affected
  by orphan removal.
- **risks / surprises carried forward**:
  - **GateGuard fact-forcing hook**: the first Edit/Write to each file
    is blocked once by a `pre:edit-write` "Fact-Forcing Gate" requiring
    you to print importers / affected symbols / data shape / the user
    instruction, then retry the SAME edit verbatim. The first Bash call
    is likewise blocked by `pre:bash:gateguard-fact-force`. Budget one
    rejected attempt per file + one for the first bash. (Confirmed again
    in M2 — fired on models.py, context.py, snip.py, test_snip.py,
    PROGRESS.md, HANDOFF.md, and the first bash.)
  - **`should_compact` legacy path**: keep the M1 legacy
    `compact_threshold` second-trigger alive — the aggressive preset and
    tiny-budget demos fire compaction purely through it (the 30k
    min_session_tokens floor blocks the PDF formula in small budgets).
    M3 touches `_force_compact`/`compact()` signatures; do not disturb
    `should_compact`.
  - **CompactSummary going frozen**: it is constructed in `compact.py`
    and read in `context.py`/`loop.py`/session persistence
    (`session_store.py`, `transcript.py` round-trips). Grep every
    `CompactSummary(` construction + every field write before freezing
    it; `restored_files` already exists as a list field, so the
    persistence layer already serializes summary fields — confirm
    `recent_file_snapshots` round-trips or is excluded deliberately.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M3.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
