# HANDOFF — Next: M2 (engine-snip-orphan-and-ancient-pairs)

> Updated by: M1 (compact-thresholds-and-llm-default)
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-pdf-align`
- **current milestone**: `M1` — DONE
- **next milestone**: `M2` — engine-snip-orphan-and-ancient-pairs
- **all milestones (per PLAN)**: M1 [done], M2 [next], M3 [pending], M4 [pending]

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

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `[ctx-pdf/M1] ...` (run `git -C python-replica log --oneline -3`)
- **tests**: 632 passing
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

## 5. Next milestone guidance

For `M2` — engine-snip-orphan-and-ancient-pairs:

- **next scope** (paraphrased from PLAN; config.yaml is authoritative):
  expand engine-driven `SnipTool.snip()` from "fold redundant fresh
  results" to also (1) DELETE (not fold) orphan `tool_use` blocks whose
  paired `tool_result` is missing and orphan `tool_result` blocks whose
  paired `tool_use` is missing; (2) DELETE paired
  `(tool_use, tool_result)` blocks whose tool_result content equals
  `CLEARED_TOOL_RESULT_CONTENT` once the summed estimated tokens of all
  such cleared placeholders reach a configurable
  `ancient_cleared_threshold_tokens` (default 10_000), oldest-first; and
  (3) insert exactly one `SNIP_BOUNDARY` marker at the earliest deletion
  site on any snip that actually deleted. Add a new
  `MessageType.SNIP_BOUNDARY` + `Message.snip_boundary()` classmethod
  (`is_meta=True`), filtered out of `context._normalize_messages()` the
  same way `COMPACT_BOUNDARY` is. `SnipTool.should_snip()` gains a new
  True branch for "cleared tokens >= threshold". Existing fold-only
  behaviour for fresh results MUST remain intact. Exit gate: pytest
  +>=12 from the 615 baseline.
- **relevant files**: `src/simple_coding_agent/snip.py` (primary),
  `src/simple_coding_agent/models.py` (new `MessageType.SNIP_BOUNDARY`
  + `Message.snip_boundary()`), `src/simple_coding_agent/context.py`
  (extend the `_normalize_messages` meta-filter to drop SNIP_BOUNDARY).
  `compact.py` already exports `CLEARED_TOOL_RESULT_CONTENT` and
  `COMPACTABLE_TOOLS` — reuse them; do not redefine.
- **expected tests**: extend `tests/test_snip.py` (orphan deletion both
  directions, ancient-cleared-pair deletion at/over threshold,
  oldest-first eviction, SNIP_BOUNDARY inserted once at earliest
  deletion, no-op when nothing deleted); possibly `tests/test_context.py`
  for the SNIP_BOUNDARY normalize-filter. Token threshold computation:
  sum `ContextBudget.estimate_tokens(json.dumps(message_dict))` over
  messages bearing a cleared ToolResult.
- **risks / surprises from M1**:
  - **GateGuard fact-forcing hook**: every first Edit/Write to a file
    in this session was blocked once by a `pre:edit-write` "Fact-Forcing
    Gate" requiring you to print importers / affected symbols / data
    shape / the user instruction, then retry the SAME edit. Budget for
    one rejected attempt per file. A `pre:bash:gateguard-fact-force`
    gate likewise blocks the first Bash call until you print the request
    + what the command verifies.
  - **`should_compact` interaction that surprised M1**: the new formula
    NEVER fires in the aggressive preset / tiny-budget demos because the
    30k `min_session_tokens` floor dominates a 4k-token budget. Those
    demos fire compaction PURELY via the legacy `compact_threshold=0.2`
    ratio. If M2 (or any later milestone) touches `should_compact` or
    the preset, keep the legacy path live or the demos go dark.
  - **`keep_recent` blast radius**: changing a constructor DEFAULT that
    `AgentLoop` auto-constructs ripples into runtime/metrics/demo tests,
    not just unit tests. When M2 changes snip defaults, grep for every
    `SnipTool()` / `_make_loop(... snip_tool=None ...)` call site
    (test_loop, test_snip, test_metrics_collector, demos) BEFORE
    assuming "additive".
  - `_normalize_messages` already filters `COMPACT_BOUNDARY` and
    `ATTACHMENT`; confirm the SNIP_BOUNDARY filter lands in the same
    branch and that `RuleBasedSummarizer.summarize` (compact.py) also
    skips SNIP_BOUNDARY like it skips COMPACT_BOUNDARY/ATTACHMENT.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M2.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
