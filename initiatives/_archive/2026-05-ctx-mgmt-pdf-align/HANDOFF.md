# HANDOFF — Initiative complete: review + wrap-up next

> Updated by: M4 (model-driven-snip-tool) — last milestone
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-pdf-align`
- **current milestone**: `M4` — DONE (last milestone of the initiative)
- **next milestone**: none — the autonomous loop will spawn the review +
  wrap-up session that audits the four shipped milestones, writes
  `REVIEW.md`, applies Tier A / B doc edits, and archives
  `initiatives/current/` into
  `initiatives/_archive/2026-05-ctx-mgmt-pdf-align/`.
- **all milestones (per PLAN)**: M1 [done], M2 [done], M3 [done], M4 [done]

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

### M4

- **commit**: `[ctx-pdf/M4] model-driven-snip-tool` (SHA in `git log`)
- **files changed**: `src/simple_coding_agent/snip_tool_model.py` [new],
  `src/simple_coding_agent/tool_registry_factory.py`,
  `src/simple_coding_agent/context.py`,
  `src/simple_coding_agent/loop.py`,
  `src/simple_coding_agent/cli.py`,
  `src/simple_coding_agent/openai_cli.py`,
  `tests/test_snip_tool_model.py` [new],
  `tests/test_loop.py`, `tests/test_context.py`,
  `tests/test_agent_integration.py`
- **tests added**: +16 `tests/test_snip_tool_model.py` (new), +12
  `tests/test_loop.py`, +6 `tests/test_context.py`, +0
  `tests/test_agent_integration.py` (an existing case modified in place
  for the six-tool registry, no net add). Total: 670 →
  704 (+34, above the >=15 floor). [corrected 2026-05-24: the original
  record claimed `685 → 704 (+19)`; the true M3-post baseline at commit
  `646bf2c` is 670 and the real delta is +34, verified via `git worktree`
  + `pytest --collect-only` per file.]
- **behavior implemented**: Model-driven `snip_history` tool +
  `<msg uuid="...">` wrap + 10k-token nudge. Five pieces.
  (1) New `src/simple_coding_agent/snip_tool_model.py` exports a pure
  `evaluate_snip_request(messages, message_uuids, *, keep_recent=5)`
  that returns a `SnipOutcome` (refused/removed_uuids) without mutation;
  a helper `snippable_candidate_uuids()` lists currently-snippable
  tool_result uuids (excludes the latest 5, excludes anything past the
  latest user-text); and `register_snip_history_tool(registry,
  transcript)` registers a tool whose `fn` captures the live `Transcript`
  by closure and on a valid request does `transcript.replace_all(filtered)`
  + returns `"Snipped <N> messages"`. Refusals raise
  `SnipRefusedError(f"snip refused: {reason}")` so `ToolExecutor` flags
  `is_error=True`. The frozen dataclass `SnipNudge(candidate_uuids:
  tuple[str, ...])` carries the candidate set; `SnipNudge.render()` emits
  the system-reminder body listing those uuids. (2) `tool_registry_factory.
  build_default_registry()` gained an optional `transcript: Transcript |
  None = None` kwarg and calls `register_snip_history_tool(registry,
  transcript or Transcript())` after the five coding tools. (3)
  `context._normalize_messages()` wraps every TOOL_RESULT block's content
  in `<msg uuid="<uuid>">...</msg>` (gated on `msg.type ==
  MessageType.TOOL_RESULT`, so ATTACHMENT user-role messages stay
  unwrapped — M3 invariant preserved). `ContextBuilder.build()` gained a
  keyword-only `snip_nudge: SnipNudge | None = None` kwarg; when present
  a single user-role nudge dict is prepended AFTER trim +
  `_remove_orphan_tool_results` and AFTER attachments, so the final
  front-to-back order is `[*attachments, nudge, *kept]`. (4)
  `AgentLoop.__init__` gained `snip_nudge_growth_tokens: int = 10_000`
  (validated `>= 1`); `_tokens_since_last_snip = 0` and
  `_snip_nudge_suppressed = False` track the window state. After every
  `_handle_tool_calls()` return in both `run()` and `run_stream()`,
  `_track_snip_nudge_growth(asst_msg, tool_results)` runs: a successful
  `snip_history` call (`_snipped_via_tool` returns True) resets the
  window to 0; any other turn accumulates the estimated tokens of the
  call inputs + result bodies. `_force_compact()` and `_maybe_snip()`
  both reset the window to 0. `_compute_snip_nudge()` arms a `SnipNudge`
  iff `not _snip_nudge_suppressed AND tokens >= threshold AND
  snippable_candidate_uuids(...)` is non-empty — silent skip otherwise.
  Both run loops pass `snip_nudge=self._compute_snip_nudge()` to
  `ContextBuilder.build()`. When `reactive_compact_attempted = True`
  flips, `_snip_nudge_suppressed = True` is set in the same code path,
  latching for the loop's lifetime. (5) `cli._run_demo`,
  `cli._build_repl_loop`, and `openai_cli._run_task` were reworded so
  the Transcript is constructed BEFORE `build_default_registry()` and
  passed in — the registry's `snip_history` closure now points at the
  exact same Transcript the AgentLoop holds. `_run_openai_repl` was not
  touched: it delegates to `cli._build_repl_loop`.
- **design decisions / deviations from PLAN**:
  - `nudge sits AFTER attachments, BEFORE kept`: the HANDOFF M3 →
    Section 5 "M3 surprises M4 must know about" called this out as the
    decision to pin. We chose `[*attachments, nudge, *kept]` because
    attachments are visible recent-file content (analogous to a
    compact-boundary marker) while the nudge is a transient instruction;
    putting the nudge between the two keeps the "snip the older,
    re-attached recent files are fresh" framing the PDF describes. Pinned
    by `test_build_nudge_follows_attachments_precedes_kept`.
  - `nudge gated on candidate non-emptiness, not just token growth`: a
    nudge with no candidate uuids would tell the model "you can snip
    these: " (empty) which is worse than silent. `_compute_snip_nudge`
    returns `None` whenever `snippable_candidate_uuids` is empty even if
    the growth threshold has been crossed. Pinned by
    `test_compute_nudge_none_when_no_candidates`.
  - `cli.py / openai_cli.py wiring change is the §7 closure-ownership
    fix, not scope creep`: without it `register_snip_history_tool` would
    close over a dead Transcript and `snip_history` calls would mutate
    nothing the loop reads. The §7 "extra files" clause in the M4
    prompt explicitly contemplates this when "the registry and AgentLoop
    are not sharing the same Transcript instance" — they weren't before
    M4, because each call site constructed its own Transcript AFTER the
    factory. The fix is mechanical (move one line) in three places.
    Covered by the end-to-end test
    `test_model_snip_via_tool_mutates_live_transcript`.
  - `SnipRefusedError is raised, not returned`: `ToolExecutor.execute`
    catches all exceptions and returns `(str(exc), is_error=True)`. So
    raising the error gives the model a tool_result block flagged as
    error, matching M4 §4 ("bump is_error=True so the model sees the
    failure") without changing the executor signature.
  - `evaluate_snip_request short-circuits on first invalid uuid`: an
    "all-or-nothing" refusal is cleaner than partial application and
    matches Claude Code's tool semantics (tool calls either succeed
    or fail). Tests assert the first invalid uuid's reason wins.
  - `nudge body is user-role + is_meta-style content`: the nudge is
    rendered as a user-role message via `_snip_nudge_dict`. We do NOT
    add a new MessageType for it — it lives only inside the API payload
    built by `ContextBuilder.build()` and never enters the Transcript.
    The Transcript stays the canonical history; the nudge is per-build.
- **known limitations**:
  - The nudge is rebuilt on every `build()` while the growth threshold
    stays crossed — once the model snips, the window resets and the
    nudge disappears. If the model ignores the nudge for several turns
    the same body (same candidate uuids) is re-emitted. This is
    intentional: we want the model to act, not to suppress reminders.
  - `<msg uuid="...">` wraps the content STRING of the tool_result API
    block. If a provider later inspects raw tool_result block content
    expecting unwrapped text, it will see the wrap. The risk for the
    `OpenAIProvider` was discussed and is the reason for the wrap —
    OpenAI Chat Completions does not strip in-content tags. Any future
    provider adapter must NOT unwrap defensively.
  - The "future-after-latest-user-text" refusal rule uses the position
    of the LATEST plain-string user message as the cutoff. A transcript
    with no plain user message (only tool_result-bearing user messages)
    treats every result as "future" and refuses all snip requests. The
    M3-introduced ATTACHMENT messages have list content (not string),
    so they do not count as user-text and do not raise the cutoff —
    correct, since attachments are not turn boundaries.

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `[ctx-pdf/M4] model-driven-snip-tool` (run
  `git -C python-replica log --oneline -5`)
- **tests**: 704 passing
- **mypy**: clean (22 source files)
- **ruff**: clean
- **branch**: main
- **known failing checks**: none in steady-state. `tests/test_trace.py
  ::test_null_tracer_zero_overhead` is a 20ms-budget `timeit` benchmark
  introduced by the prior `observable-thresholds-harden` initiative;
  under heavy CI load it can transiently exceed the budget. It passes
  in isolation and on a quiet machine. The test self-skips when
  coverage / `sys.gettrace()` instrumentation is active. This is NOT
  M4-introduced behaviour; it predates this initiative and is unrelated
  to context-management. Re-run the suite if a single failure of this
  test appears.

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
  - **(added by M4)** `snip_history` is a registered ToolRegistry tool
    with the exact schema `{"type":"object","properties":{
    "message_uuids":{"type":"array","items":{"type":"string"}}},
    "required":["message_uuids"]}`. Do NOT widen the schema (e.g. add
    `tool_use_ids`) or rename `message_uuids`; the model's own tool-call
    semantics depend on this contract. Refusals MUST continue to raise
    `SnipRefusedError("snip refused: <reason>")` so the executor surfaces
    `is_error=True`. Return string for a successful call is exactly
    `f"Snipped {N} messages"` (singular/plural unchanged — both tests
    and the PDF intent rely on the stable shape).
  - **(added by M4)** the `snip_history` tool fn captures the live
    `Transcript` by closure. The registry and the AgentLoop MUST share
    the same `Transcript` instance — `cli._run_demo`, `cli._build_repl_loop`,
    `openai_cli._run_task` all construct the Transcript BEFORE
    `build_default_registry(workspace, transcript=...)` and pass it in.
    Any new call site that builds a registry + an AgentLoop must follow
    the same wiring or the model's snips will not reach the live history.
  - **(added by M4)** `context._normalize_messages()` wraps every
    `MessageType.TOOL_RESULT` block's content in
    `<msg uuid="<uuid>">...</msg>`. The wrap is gated on `msg.type ==
    TOOL_RESULT`, NOT on `role == USER`, so ATTACHMENT user-role
    messages (M3) stay unwrapped. A future refactor of
    `_normalize_messages` MUST preserve this gating — wrapping an
    ATTACHMENT would corrupt recent-file content the model expects to
    read verbatim.
  - **(added by M4)** `SnipNudge` is `@dataclass(frozen=True)` and lives
    in `snip_tool_model.py`. It carries `candidate_uuids: tuple[str, ...]`
    and renders as a single is_meta-style user message. The nudge lives
    ONLY inside the API payload built by `ContextBuilder.build()` — it
    is never appended to the Transcript. Do not introduce a
    `MessageType.SNIP_NUDGE`; the per-build placement is the contract.
  - **(added by M4)** `ContextBuilder.build()`'s final front-to-back
    order when both an attachment set and a nudge are present is
    `[*attachments, nudge, *kept]`. Pinned by
    `tests/test_context.py::test_build_nudge_follows_attachments_precedes_kept`.
    Any future change to attachment/nudge placement must update both
    that test AND `_attachment_dicts` / nudge-prepend in `build()`
    together — they are the joint contract.
  - **(added by M4)** `AgentLoop._tokens_since_last_snip` resets to 0 on
    EACH of: a full compact (`_force_compact`), an engine snip
    (`_maybe_snip` after `replace_all`), and a successful model snip
    (the `snip_history` call returned without `is_error`). All three
    reset sites must stay live; a regression that drops one of them
    would arm the nudge spuriously.
  - **(added by M4)** Once `reactive_compact_attempted` flips True in
    `AgentLoop.run()` / `run_stream()`, `_snip_nudge_suppressed = True`
    is set in the same code path and latches for the loop's lifetime.
    `_compute_snip_nudge()` returns `None` while suppressed. Both run
    methods must set the flag the moment they detect reactive compact;
    if a new control-flow branch reaches `_force_compact()` via
    `PromptTooLongError`, it must also set the suppression flag.

## 5. Next milestone guidance

Initiative complete. Next agent is the review session spawned by
`automation/scripts/run_all_milestones.sh` after this commit lands. The
review session audits all four shipped milestones (M1–M4), writes
`initiatives/current/REVIEW.md`, applies Tier A / B doc edits (the new
public symbols `snip_history` tool, `SnipNudge`, `register_snip_history_tool`,
`evaluate_snip_request`, `snippable_candidate_uuids`,
`AgentLoop.snip_nudge_growth_tokens`), and archives
`initiatives/current/` into
`initiatives/_archive/2026-05-ctx-mgmt-pdf-align/`.

**Audit focus areas for the review session:**

- **(a)** does the `snip_history` tool actually work end-to-end with
  `OpenAIProvider` via `openai_cli`? The model needs to (1) see uuids
  in `<msg uuid="...">` wraps inside tool_result content, (2) emit a
  valid `snip_history` tool call whose arguments parse as
  `{"message_uuids": [...]}`, (3) have its call routed to the
  `ToolExecutor` whose registry was built from the SAME Transcript the
  AgentLoop holds. Wiring is in `openai_cli._run_task` (one-shot) and
  `openai_cli._run_openai_repl` → `cli._build_repl_loop` (REPL). A live
  smoke run is the only way to confirm OpenAI Chat Completions does not
  silently strip or rewrite the in-content `<msg uuid="...">` tags.

- **(b)** does the `<msg uuid="...">` wrap survive OpenAI's
  serialization without truncation? The wrap is applied by
  `context._normalize_messages()` and lives inside the `content` field
  of tool_result API blocks. Verify: (1) the tag is present in the
  serialized HTTP request body, (2) no truncation when content is large
  enough to be externalized (`ToolResultStore`-replaced content already
  carries a `<persisted-output>` tag; the M4 wrap goes OUTSIDE it
  giving `<msg uuid="..."><persisted-output ...>...</persisted-output></msg>`
  — check this nests rather than overwrites), (3) the model's reply
  references uuids correctly (no hallucinated uuids, no truncated
  uuids).

- **(c)** do all 4 milestones' invariants in Section 4 still hold?
  Walk the M1, M2, M3, and M4 entries in Section 4 and grep / read the
  current source to confirm each is intact. Pay particular attention
  to (M1) `MicroCompactor.keep_recent=5` default and the legacy
  `compact_threshold` second-trigger; (M2) `MessageType.SNIP_BOUNDARY`
  still filtered in `_normalize_messages` and
  `_remove_orphan_tool_results` still live; (M3)
  `CompactSummary` still frozen with `recent_file_snapshots: tuple` and
  ATTACHMENT still passes through `_normalize_messages`; (M4) the
  `<msg uuid="...">` wrap gates on `msg.type == TOOL_RESULT` not
  `role == USER`.

- **(d)** is the registry/AgentLoop transcript-sharing wiring complete
  at every call site? Grep for `Transcript()` constructor calls inside
  `src/simple_coding_agent/` and confirm each one either (i) is fed
  into `build_default_registry(..., transcript=...)` immediately, or
  (ii) is documented as a non-AgentLoop use (e.g. a test fixture). A
  dangling `Transcript()` constructed AFTER `build_default_registry`
  would silently break model snips.
