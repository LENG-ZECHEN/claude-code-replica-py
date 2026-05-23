---
slug: ctx-mgmt-pdf-align
commit_prefix: ctx-pdf

milestones:
  M1:
    name: compact-thresholds-and-llm-default
    phase_ids: [A1, A2, A3]
    exit_gate: |
      pytest --tb=no -q passes with count grown by >=10 from baseline AND
      MicroCompactor.microcompact() preserves the 5 most recent
      compactable tool_results (new param keep_recent: int = 5;
      pre-PDF default-behaviour test still passes when explicitly
      constructed with keep_recent=0) AND
      ContextCompactor.should_compact() returns True iff
      `used >= context_window - output_headroom - compact_headroom`
      AND `used >= min_session_tokens`, with defaults
      output_headroom=12_000, compact_headroom=20_000,
      min_session_tokens=30_000 AND
      ContextCompactor() default summarizer is LLMSummarizer when a
      Provider is supplied via a new `provider` kwarg; remains
      RuleBasedSummarizer when provider=None (backward compat).
    notes: |
      PDF reference: §3 microcompact "keep latest 5"; §4 autoCompact
      threshold formula `context_window - output_headroom(12k) -
      compact_headroom(20k)` with min_session_tokens(30k) floor; §4
      default summarizer is LLM-based.
      All three deltas are pure additions to existing compact.py
      classes. Backward-compat strategy: new constructor params
      (`keep_recent`, `output_headroom`, `compact_headroom`,
      `min_session_tokens`, `provider`) get PDF-aligned defaults; the
      single-ratio `compact_threshold` param is preserved as a SECOND
      legacy trigger (should_compact returns True if EITHER the new
      formula fires OR the old ratio fires) so the aggressive preset
      still works.
      CLI flags `--microcompact-keep-recent`, `--output-headroom`,
      `--compact-headroom`, `--min-session-tokens` propagate through
      `cli._resolve_threshold` so the existing `--aggressive-thresholds`
      preset can still override.
      Do NOT change `_build_repl_loop`'s compactor wiring to actually
      pass a provider yet — that's a separate decision for the wrap-up
      review. M1 only adds the surface.

  M2:
    name: engine-snip-orphan-and-ancient-pairs
    phase_ids: [B1, B2, B3]
    exit_gate: |
      pytest --tb=no -q passes with count grown by >=12 from baseline
      AND
      SnipTool.snip() deletes (not folds) tool_use blocks whose paired
      tool_result is missing AND tool_result blocks whose paired
      tool_use is missing (taking over orphan handling from
      context._remove_orphan_tool_results for the snip phase) AND
      SnipTool.snip() deletes paired (tool_use, tool_result) blocks
      when their tool_result content equals
      CLEARED_TOOL_RESULT_CONTENT and the estimated tokens of all such
      cleared placeholders >= configurable threshold
      (`ancient_cleared_threshold_tokens`, default 10_000) AND
      every snip() invocation that actually deleted inserts exactly one
      SNIP_BOUNDARY marker at the position of the earliest deletion
      (new MessageType.SNIP_BOUNDARY, Message.snip_boundary()
      classmethod, is_meta=True, filtered out of
      context._normalize_messages() like COMPACT_BOUNDARY is).
    notes: |
      PDF reference: §3 snip "真删除 — 不留占位 + snip_boundary marker"
      (engine-side, not the model-driven variant in M4).
      Snip remains hard-coded and engine-driven at the current call
      site (loop.py:215 `_maybe_snip()`) — the user has confirmed this
      position stays. What changes: snip's responsibility expands from
      "fold redundant fresh tool results" to also "garbage-collect
      orphans and ancient cleared pairs that microcompact left
      behind".
      Token threshold computation: iterate messages, sum
      `ContextBudget.estimate_tokens(json.dumps(m))` for every message
      whose content list contains a ToolResult with content ==
      CLEARED_TOOL_RESULT_CONTENT, trigger pair-wise deletion when
      sum >= threshold. Delete oldest pairs first until sum drops
      below threshold. Removing a tool_use that empties its parent
      assistant message also removes that message.
      Existing P8 fold-only behaviour for fresh (non-cleared,
      non-orphan) results MUST remain intact — all current
      tests/test_snip.py cases must keep passing without modification.
      SnipTool.should_snip() gains a new True branch for "cleared
      tokens >= threshold" alongside the existing path-count >=3 and
      pair-count >=10 branches.

  M3:
    name: autocompact-recent-files-attachment
    phase_ids: [C1, C2]
    exit_gate: |
      pytest --tb=no -q passes with count grown by >=8 from baseline
      AND
      AgentLoop carries a `_recent_file_snapshots: deque[FileSnapshot]`
      capped at N (default 5) populated inside `_execute_one()` when a
      `read_file` call succeeds (FileSnapshot = frozen dataclass with
      `path: str`, `content: str`, `captured_at: str`) AND
      `_force_compact()` reads the current snapshot deque and passes
      it into `ContextCompactor.compact(snapshots=...)`, which stores
      it on the returned `CompactSummary.recent_file_snapshots: tuple`
      AND
      `ContextBuilder.build()` reads `compact_summary.recent_file_snapshots`
      and emits one MessageType.ATTACHMENT message per snapshot
      immediately after COMPACT_BOUNDARY and before the keep_recent
      messages; each attachment serializes as a user-role message
      whose content is `<recent-files>\n<file path="...">CONTENT</file>\n
      </recent-files>`, is_meta=True, and is NOT counted toward
      keep_recent budget trimming.
    notes: |
      PDF reference: §4 autoCompact post-restoration "recent files
      re-inject". User clarified explicitly: do NOT have the model
      re-read — snapshot file contents BEFORE compaction, then
      re-attach them in the rebuilt context as an attachment.
      MessageType.ATTACHMENT already exists in `models.py:51` but is
      unused. Confirm during M3 that
      `context._normalize_messages()` already passes ATTACHMENT
      through to API serialization; if it filters them out (like
      COMPACT_BOUNDARY), change the filter to allow ATTACHMENT
      through.
      Recent-files tracking lives on AgentLoop (not Transcript)
      because the snapshot must be the live content at the moment
      `read_file` returned, not whatever the (possibly snipped /
      microcompacted) tool_result currently shows. Hook the capture
      into `_execute_one` after the success branch of the
      `read_file` tool dispatch.
      Snapshot deque survives across compactions — after compact
      runs, snapshots stay attached to AgentLoop so the next compact
      can re-attach the same / updated set. Append eviction is
      newest-wins (deque(maxlen=N)).
      CompactSummary becomes a frozen dataclass with a new
      `recent_file_snapshots: tuple[FileSnapshot, ...] = ()` field
      (immutable default).

  M4:
    name: model-driven-snip-tool
    phase_ids: [D1, D2, D3]
    exit_gate: |
      pytest --tb=no -q passes with count grown by >=15 from baseline
      AND
      A new `snip_history` tool is registered by
      `tool_registry_factory.build_default_registry()` with
      `input_schema = {"type": "object", "properties": {
        "message_uuids": {"type": "array", "items": {"type": "string"}}
      }, "required": ["message_uuids"]}` AND
      Invoking `snip_history` with a list of message uuids removes
      those messages from the AgentLoop's live Transcript (via
      Transcript.replace_all(filtered)) and returns a string
      `"Snipped <N> messages"` AND
      `context._normalize_messages()` wraps each user-role tool_result
      message body with `<msg uuid="<uuid>">...</msg>` so the model
      sees and can target message uuids (this surface is required
      because OpenAI Chat Completions does not allow arbitrary
      per-message metadata fields) AND
      AgentLoop tracks `_tokens_since_last_snip` updated after every
      `_handle_tool_calls()` return; when growth >= configurable
      `snip_nudge_growth_tokens` (default 10_000), the next
      `ContextBuilder.build()` call prepends an is_meta=True
      system-reminder user message describing the `snip_history` tool
      and listing the uuids of currently-snippable messages
      (compactable tool_results older than the latest 5) AND
      `_tokens_since_last_snip` resets on (a) any snip — engine or
      model — and (b) any full compact AND
      Once `reactive_compact_attempted` flips True during a loop, the
      nudge is suppressed for the lifetime of that AgentLoop
      instance (snip is irrelevant after reactive compact).
    notes: |
      PDF reference: §3 snip model-driven SnipTool +
      shouldNudgeForSnips ("every ~10k tokens").
      User clarified: input schema uses `message_uuids: list[str]`
      (not tool_use_ids), and the growth check runs after each
      tool-call iteration (not just at turn boundaries).
      Implementation location: new file
      `src/simple_coding_agent/snip_tool_model.py` exporting a
      `register_snip_history_tool(registry, transcript)` helper that
      `tool_registry_factory.build_default_registry()` calls. The
      registered tool fn captures the live Transcript by closure;
      pairing with the AgentLoop's transcript happens because both
      the registry and the AgentLoop are built from the same
      Transcript instance in `_build_repl_loop`.
      Tool description must explicitly tell the model:
        - "Each tool_result you have seen is wrapped in
          <msg uuid='...'>...</msg>; pass any of those uuids."
        - "You can only snip past tool_result messages; you cannot
          snip your own most recent response or the user's current
          turn."
      Tool fn validates: each uuid exists in transcript, the matching
      message is a tool_result-bearing user message (is_meta=True
      AND content list has only ToolResult blocks), refuses to snip
      the most recent N (default 5) tool_result messages, refuses to
      snip any message later than the latest user-text message.
      Refusals return `"snip refused: <reason>"` and bump
      is_error=True so the model sees the failure.
      Nudge injection: ContextBuilder.build() gains a new optional
      kwarg `snip_nudge: SnipNudge | None = None`; when present,
      prepends one is_meta=True message before the first kept
      message. AgentLoop computes the SnipNudge when
      `_tokens_since_last_snip >= snip_nudge_growth_tokens` AND
      `not _snip_nudge_suppressed`. The SnipNudge body lists
      candidate uuids; if no candidates exist, no nudge is built
      (silent skip).

---

> Bootstrapped on 2026-05-23. Baseline commit: `8f1d98f`. Baseline pytest: 615 passing. Baseline mypy/ruff: clean. Sizing assessment: M1–M3 well within thresholds; M4 borderline on three signals (src files=4, cross-cutting components=4, new tests=~15) but does NOT strictly trip any threshold and lacks the CLI-flag surface that would fire the "combines intro+wire+CLI" criterion — no SIZING WAIVED needed. Suggested M4a/M4b split seam is documented in PLAN.md "Anything else" for reference if Phase 2 thrash occurs.

# Goal

Align the project's five-mechanism context-management pipeline with
Claude Code v2.1.88's behavior as documented in `claude_code_notes.pdf`
and evaluated side-by-side in the 2026-05-23 review session, closing
every gap **except** the forked-agent + prompt-cache-sharing
summarization optimization (explicitly out of scope — `OpenAIProvider`
has no fork primitive and the workaround would be speculative). After
this initiative, mechanisms (1) tool_result_budget, (2) microcompact,
(3) snip, (4) autoCompact, (5) reactiveCompact each match the PDF on
all four axes (touch site / trigger condition / post-trigger logic /
context-replay impact), with snip split into two coexisting flavors
per user decision.

# Background / motivation

The 2026-05-23 evaluation produced this gap inventory against the PDF
rubric:

- **Mechanism 1 (tool_result_budget):** ✅ 1:1 with PDF — no change.
- **Mechanism 2 (microcompact):** 🟡 missing `keep_recent=5`; clears
  too aggressively.
- **Mechanism 3 (snip):** ❌ entirely different paradigm. PDF =
  model-driven SnipTool + 10k nudge + real delete. Replica = engine
  hardcoded + fold-only. User decided: keep the engine version at its
  current loop position AND add the PDF's model-driven version
  alongside it, so engine snip handles GC and model snip handles
  selective deletion.
- **Mechanism 4 (autoCompact):** 🟡 single-ratio threshold instead of
  PDF's double-headroom subtraction; default RuleBasedSummarizer
  instead of LLMSummarizer; no post-compaction recent-files
  restoration.
- **Mechanism 5 (reactiveCompact):** ✅ structure 1:1 (inherits §4
  fixes automatically).

User explicitly resolved three ambiguous design points in this
session:

1. **Engine snip threshold for deleting microcompact-placeholders:**
   by accumulated cleared-placeholder token count (~10k), not message
   count or transcript ratio.
2. **Recent-files restoration after autoCompact:** snapshot file
   contents BEFORE compaction and re-inject as attachment in the
   rebuilt context. Do NOT have the model re-read.
3. **Model SnipTool input format:** `message_uuids: list[str]`, not
   tool_use_ids.

# Design sketch

```
Per-turn pipeline (loop.py:213-253), POST-initiative
─────────────────────────────────────────────────────
turn N:
    _maybe_microcompact()      ← M1: + keep_recent=5
    _maybe_engine_snip()       ← M2: orphan + ancient-pair deletion
                                       + SNIP_BOUNDARY marker
    _maybe_compact()           ← M1: double-headroom threshold +
                                       min_session_tokens floor
                                  M3: snapshot _recent_file_snapshots
                                       into CompactSummary
    while True:
        ContextBuilder.build()  ← M3: inject ATTACHMENT messages from
                                       CompactSummary
                                  M4: inject snip nudge when
                                       tokens-since-last-snip >= 10k;
                                       wrap tool_results with
                                       <msg uuid="..."> for targeting
        provider.call()
        break on success
        except PromptTooLongError: _force_compact() (one-shot guard)
    if response.tool_calls:
        _handle_tool_calls()
        _check_snip_nudge()    ← M4: NEW — track token growth,
                                       arm nudge for next build()

ContextCompactor.should_compact():
    OLD: used > available_tokens * compact_threshold
    NEW: (used >= context_window - output_headroom(12k)
                                 - compact_headroom(20k)
          AND used >= min_session_tokens(30k))
         OR  used > available_tokens * compact_threshold (legacy)

ContextCompactor()._summarizer:
    OLD: RuleBasedSummarizer (always)
    NEW: LLMSummarizer when provider kwarg supplied,
         RuleBasedSummarizer fallback when not
         (no forked-agent / cache-sharing optimization — OUT OF SCOPE)

SnipTool.snip() (engine, M2):
    Phase 1 (existing): fold redundant fresh results
    Phase 2 (NEW): delete orphan tool_use AND orphan tool_result
    Phase 3 (NEW): delete paired (tool_use, tool_result) when their
                   tool_result content is CLEARED_TOOL_RESULT_CONTENT
                   AND sum of cleared-placeholder tokens >= 10k
    Phase 4 (NEW): insert SNIP_BOUNDARY at earliest deletion site

NEW snip_history(message_uuids) tool (M4):
    Registered in tool_registry_factory.build_default_registry()
    Captures live Transcript by closure
    Validates uuids; refuses to snip recent / non-tool_result / future
    Removes named uuids via Transcript.replace_all(filtered)
    Returns "Snipped N messages" or "snip refused: <reason>"

NEW AgentLoop state:
    M3: _recent_file_snapshots: deque[FileSnapshot]   (cap 5)
    M4: _tokens_since_last_snip: int
    M4: _snip_nudge_suppressed: bool  (flips true after reactive)
```

# Risks / known unknowns

- **OpenAI Chat Completions strips arbitrary per-message keys.** M4's
  uuid visibility must use in-content wrapping (`<msg uuid="...">`),
  not a sibling `metadata` field. Confirmed in advance via the
  exploration report; no `metadata`-key experiment is needed.
- **Changing `ContextCompactor` default summarizer (M1)** may break
  existing tests that assume the rule-based 9-section output. M1 must
  scope changes so all current `tests/test_compact.py` cases pass
  unmodified when `provider=None`; new cases cover the
  `provider=MockProvider(...)` branch.
- **`ATTACHMENT` messages exist in `models.py:51` but appear unused.**
  M3 must confirm `context._normalize_messages()` either passes them
  through or change the filter to allow them. Likewise verify the
  budget-trim loop does not pop them preferentially.
- **Engine snip absorbing orphan-detection (M2)** creates an ordering
  dependency: snip must run before `ContextBuilder.build()`'s own
  `_remove_orphan_tool_results()`. Already the case
  (loop.py:215 vs the build call at loop.py:225) — M2 must verify no
  other code path calls `_remove_orphan_tool_results()` post-snip and
  re-introduces zombies.
- **Token-growth nudge cadence (M4) could bloat system prompt.** Cap
  at one nudge per turn, suppress after reactive compact fires
  (already in exit gate). If a pathological loop still emits nudges
  every turn, the suppression escape hatch is reactive compact —
  acceptable degenerate behaviour.
- **`Transcript.replace_all()` is the only mutation API**; both M2 and
  M4 converge on it. Message UUIDs are stable across rebuilds
  (assigned at `Message.__init__`), so M4's snip_history tool can
  safely target uuids the model saw in a prior turn.

# Out of scope (this initiative)

- **Forked agent + prompt-cache sharing for LLMSummarizer.**
  `OpenAIProvider` has no fork primitive; speculative implementation
  is deferred until an Anthropic-API provider ships.
- **Todo / plan-state / hook-output restoration after autoCompact.**
  None of these mechanisms exist in the replica; their restoration
  surfaces will get separate initiatives when they ship.
- **Snip / engine-snip behavior for `write_file` / `edit` tools.**
  Side-effecting tool results stay untouched (P8 invariant).
- **Tool-result externalization (mechanism 1).** Already 1:1 with
  PDF including prompt-cache stability via `ContentReplacementState`.
  Do not touch `tool_result_store.py` in any milestone of this
  initiative.
- **`_remove_orphan_tool_results()` removal.** M2 leaves it in place
  as a defence-in-depth safety net — snip handles orphans normally,
  the build-time pass remains as backstop for edge cases.

# Anything else

The PDF reference (`claude_code_notes.pdf`) is a user-owned document
NOT in the repo. The 2026-05-23 side-by-side evaluation against it is
the live source of truth for "PDF says X" claims — each milestone's
`notes` field cites the specific PDF section being aligned. Phase 1
need not re-derive these from the PDF; the gap inventory in
"Background / motivation" above is the canonical input.

Test count budget per milestone (rough estimate, Phase 1 free to
adjust): M1 +10, M2 +12, M3 +8, M4 +15. Total ≈ +45 tests.

Current baseline (from `observable-thresholds-harden` M3 commit
`9b00767`): pytest 615 passing, mypy clean, ruff clean.

Phase 1 sizing reassessment: M1–M3 each comfortably fit the single-
session envelope. M4 is the only one near the 6-src-file guideline.

> SIZING WAIVED for M4: bundles new tool + uuid plumbing + nudge
> injection because they form a tight coupling. The tool is useless
> without uuid visibility; uuid visibility is wasted without the
> nudge; the nudge has no target without the tool. Splitting would
> force throwaway test scaffolding. Expected files touched: 5–6 in
> `src/` (one over the 6-file guideline), ~15 new tests. If Phase 1's
> sizing reassessment disagrees, the suggested seam is:
> - **M4a** — snip_history tool + uuid serialization + tool-side tests
> - **M4b** — token-growth nudge + reminder injection + nudge tests
>
> M4b depends on M4a; M4a is shippable independently.
