# HANDOFF — Next: M4 (model-driven-snip-tool)

> Updated by: M3 (autocompact-recent-files-attachment)
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-pdf-align`
- **current milestone**: `M3` — DONE
- **next milestone**: `M4` — model-driven-snip-tool
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [next]

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

### M3

- **commit**: `[ctx-pdf/M3] autocompact-recent-files-attachment` (SHA in `git log`)
- **files changed**: `src/simple_coding_agent/models.py`,
  `src/simple_coding_agent/compact.py`,
  `src/simple_coding_agent/context.py`,
  `src/simple_coding_agent/loop.py`, `tests/test_models.py`,
  `tests/test_compact.py`, `tests/test_context.py`, `tests/test_loop.py`
- **tests added**: +7 test_models.py, +3 test_compact.py, +6 test_context.py,
  +7 test_loop.py. Total: 647 → 670 (+23).
- **behavior implemented**: Recent-file snapshot capture + post-compaction
  re-attachment (PDF §4 "recent files re-inject"). Four pieces.
  (1) New `FileSnapshot` frozen dataclass in `models.py` (`path`,
  `content`, `captured_at`). (2) `AgentLoop` carries
  `_recent_file_snapshots: deque[FileSnapshot]` (capacity ctor kwarg
  `recent_files_capacity: int = 5`, validated `>= 1`). `_execute_one`
  calls a new `_capture_file_snapshot(call, content)` when
  `call.name == "read_file" and not is_error`, capturing the RAW returned
  content BEFORE `ToolResultStore` externalization. Eviction is
  newest-wins per-path (a re-read of an already-tracked path removes the
  prior entry, then appends; the deque's `maxlen` caps total). (3)
  `CompactSummary` is now `@dataclass(frozen=True)` with a new
  `recent_file_snapshots: tuple[FileSnapshot, ...] = ()` field;
  `ContextCompactor.compact()` gained a keyword-only `snapshots` param
  stored verbatim on the returned summary (both the n==0 and main paths).
  `_force_compact()` reads `tuple(self._recent_file_snapshots)` ONCE and
  passes it in. (4) `Message.attachment(path, content)` factory (USER
  role, `MessageType.ATTACHMENT`, `is_meta=True`, content
  `<recent-files>\n<file path="...">CONTENT</file>\n</recent-files>`).
  `context._normalize_messages()` no longer filters ATTACHMENT (only
  COMPACT_BOUNDARY/SNIP_BOUNDARY remain in the drop tuple), so attachments
  serialize as user messages. `ContextBuilder.build()` builds attachment
  dicts via new module helper `_attachment_dicts(compact_summary)` and
  PREPENDS them to `api_messages` AFTER the budget-trim loop +
  `_remove_orphan_tool_results`, so they land after the (stripped) compact
  boundary, before the kept messages, and are never popped by trimming.
- **design decisions / deviations from PLAN**:
  - `attachments injected after trim, not before`: the exit gate says
    attachments are "NOT counted toward keep_recent budget trimming" and a
    test asserts "budget-trim does not pop ATTACHMENT preferentially". The
    cleanest way to honor both is to run the trim loop on the kept messages
    only, then prepend the attachment dicts. They are therefore never trim
    candidates and always survive. Their tokens ARE included in the final
    `estimated_tokens` (accurate reporting) but do not drive trimming.
  - `attachments normalized individually`: `_attachment_dicts` calls
    `_normalize_messages([msg])` per snapshot so consecutive same-role
    (USER) attachments are NOT merged into one block — one snapshot maps to
    exactly one `<recent-files>` message dict, as the gate requires.
  - `snapshot captures raw content, not the tool_result`: per the PLAN
    note, capture happens in `_execute_one` on the value read_file
    returned, BEFORE externalization / microcompact / snip can alter the
    in-transcript `tool_result`. So a later-cleared placeholder never
    overwrites the re-attached body.
  - `snapshots not persisted by session_store`: `_summary_to_dict` /
    `_summary_from_dict` were left untouched; the new field defaults to
    `()`, so a resumed `CompactSummary` simply has empty snapshots. This is
    deliberate — snapshots are live AgentLoop state re-captured on the next
    read_file, and a stale cross-process snapshot would be misleading.
  - `_CountingCompactor test double updated`: its `compact()` override
    (test_loop.py) now forwards `**kwargs` so the reactive-compact path
    (which calls `_force_compact()` → `compact(snapshots=...)`) keeps
    working. Necessary because `snapshots` is a new keyword-only param.
- **known limitations**:
  - Snapshot content is captured raw and uncapped in size; a very large
    read_file body is re-attached in full after compaction (by design —
    the point is to avoid a re-read). The budget-trim loop does not bound
    attachments, so a pathologically large recent-file set could exceed the
    nominal budget in the rebuilt context. Acceptable for the replica;
    real Claude Code bounds the recent-files set similarly by count (5).
  - Attachments are re-emitted on EVERY `build()` while the same
    `CompactSummary` is the active `_last_summary` — they persist across
    turns until the next compaction replaces the summary. This matches the
    "re-inject after restoration" intent.

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `[ctx-pdf/M3] ...` (run `git -C python-replica log --oneline -3`)
- **tests**: 670 passing
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
  - **(added by M3)** `CompactSummary` is now `@dataclass(frozen=True)`
    with a `recent_file_snapshots: tuple[FileSnapshot, ...] = ()` field.
    This is part of the CompactSummary contract — M4 must NOT break it:
    do not unfreeze it, do not change the field to a list, and do not drop
    it from `compact()`'s output. Callers must rebind (not mutate) summary
    instances (use `dataclasses.replace` if a copy-with-change is needed).
  - **(added by M3)** `MessageType.ATTACHMENT` MUST stay filtered-IN: it
    passes through `context._normalize_messages()` to API serialization
    (it is real user-role content), UNLIKE COMPACT_BOUNDARY and
    SNIP_BOUNDARY which stay filtered OUT. M4 must NOT add ATTACHMENT back
    into the normalize drop tuple, and any new serialization path must
    likewise let ATTACHMENT through while dropping the two boundary types.
  - **(added by M3)** `FileSnapshot` is frozen and lives in `models.py`.
    The `AgentLoop._recent_file_snapshots` deque is mutable (that is its
    job) but each snapshot inside it is immutable. Capture happens ONLY for
    successful `read_file` calls (not write_file/edit/etc.), in
    `_execute_one`, on the raw pre-externalization content.

## 5. Next milestone guidance

For `M4` — model-driven-snip-tool:

- **next scope** (paraphrased from PLAN; config.yaml is authoritative):
  add the model-driven `snip_history` tool + `<msg uuid="...">`
  serialization + a 10k-token nudge. Pieces: (1) new
  `snip_history` tool registered by
  `tool_registry_factory.build_default_registry()` with
  `input_schema = {"type":"object","properties":{"message_uuids":
  {"type":"array","items":{"type":"string"}}},"required":["message_uuids"]}`;
  invoking it removes those messages from the AgentLoop's live Transcript
  via `Transcript.replace_all(filtered)` and returns `"Snipped <N>
  messages"`. (2) `context._normalize_messages()` wraps each user-role
  tool_result message body with `<msg uuid="<uuid>">...</msg>` so the
  model can target uuids (OpenAI Chat Completions strips arbitrary
  per-message metadata). (3) `AgentLoop` tracks
  `_tokens_since_last_snip` updated after every `_handle_tool_calls()`
  return; when growth >= `snip_nudge_growth_tokens` (default 10_000), the
  next `build()` prepends an `is_meta=True` system-reminder user message
  describing `snip_history` and listing currently-snippable uuids
  (compactable tool_results older than the latest 5). Resets on any snip
  (engine or model) and any full compact. Suppressed for the loop's
  lifetime once `reactive_compact_attempted` flips True. Exit gate:
  pytest +>=15 from baseline (655+ → expect ~685+ given M3 landed at 670).
- **likely-touched files**: new `src/simple_coding_agent/snip_tool_model.py`
  (exports `register_snip_history_tool(registry, transcript)`),
  `tool_registry_factory.py` (calls the register helper),
  `loop.py` (`_tokens_since_last_snip` state + reset points + nudge
  arming after `_handle_tool_calls`), `context.py`
  (`<msg uuid="...">` wrapping in `_normalize_messages` + a new
  `build(snip_nudge=...)` kwarg that prepends one is_meta message before
  the first kept message), plus `SnipNudge` dataclass.
- **M3 surprises M4 must know about `build()` + attachment placement**:
  - M3 prepends recent-file ATTACHMENT dicts at the FRONT of
    `api_messages`, AFTER the trim loop + `_remove_orphan_tool_results`.
    M4's snip-nudge message is ALSO supposed to be prepended "before the
    first kept message". DECIDE the relative order of nudge vs
    attachments deliberately — the PDF intent is: compact boundary →
    (recent-files attachments) → (snip nudge / kept turns). Cleanest is to
    prepend the nudge AFTER the attachments are prepended so the final
    front-to-back order is `[*attachments, nudge, *kept]`, OR
    `[nudge, *attachments, *kept]` if you treat the nudge as the very
    first system-reminder. Either is defensible; pick one and pin it with
    a test. The existing `_attachment_dicts(compact_summary)` helper is
    the integration point — do not re-merge attachments with kept messages.
  - `_normalize_messages` is the shared serialization choke point. M3 made
    it pass ATTACHMENT through. M4's `<msg uuid="...">` wrapping must wrap
    ONLY the tool_result-bearing USER messages and must NOT wrap ATTACHMENT
    messages (those are recent-file content, not snippable history) — gate
    on `msg.type == TOOL_RESULT` (or the `is_meta + only-ToolResult-blocks`
    shape the PLAN names), NOT on `role == USER` alone, or you will wrap
    the M3 attachments too.
  - `CompactSummary` is frozen now (see Section 4). If M4 needs to attach
    nudge state to the summary (it should NOT — nudge is AgentLoop state),
    use AgentLoop fields, not summary mutation.
- **risks / surprises carried forward**:
  - **GateGuard fact-forcing hook**: the first Edit/Write to each file
    is blocked once by a `pre:edit-write` "Fact-Forcing Gate" requiring
    you to print importers / affected symbols / data shape / the user
    instruction, then retry the SAME edit verbatim. The first Bash call
    is likewise blocked by `pre:bash:gateguard-fact-force`. Budget one
    rejected attempt per file + one for the first bash. (Confirmed again
    in M3 — fired on every src + test file edited, PROGRESS.md,
    HANDOFF.md, and the first bash.) Also note: `cd python-replica`
    persists working dir across Bash calls, so a second `cd python-replica`
    fails with "no such file or directory" — use absolute paths or rely on
    the persisted cwd.
  - **`should_compact` legacy path**: keep the M1 legacy
    `compact_threshold` second-trigger alive — the aggressive preset and
    tiny-budget demos fire compaction purely through it (the 30k
    min_session_tokens floor blocks the PDF formula in small budgets).
    Do not disturb `should_compact`.
  - **`Transcript.replace_all()` is the only mutation API** — M4's
    `snip_history` tool fn uses it (same as engine snip/microcompact). The
    tool captures the live Transcript by closure; pairing works because
    the registry and AgentLoop share one Transcript instance in
    `_build_repl_loop`.
  - **M4 is the sizing-borderline milestone** (PLAN flagged 5–6 src files,
    ~15 new tests). The PLAN documents an M4a/M4b split seam (tool+uuid
    first, nudge second) if Phase 2 thrash occurs. M4a is shippable
    independently; M4b depends on it.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M4.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
