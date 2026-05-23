# HANDOFF — Next: M1 (compact-thresholds-and-llm-default)

> Updated by: Phase 1 bootstrap of `ctx-mgmt-pdf-align`
> Date: 2026-05-23
> Re-verify Section 3 numbers before starting work — do not trust this
> file blindly.

---

## 1. Current initiative

- **slug**: `ctx-mgmt-pdf-align`
- **current milestone**: _(not started)_
- **next milestone**: `M1` — compact-thresholds-and-llm-default
- **all milestones (per PLAN)**: M1 [next], M2 [pending], M3 [pending], M4 [pending]

## 2. Completed milestones

_(none yet — this initiative has not started)_

<!--
After each milestone, the milestone agent APPENDS one subsection like:

### M{N}

- **commit**: `<sha>` `[ctx-pdf/M{N}] <subject>`
- **files changed**: `<file1>`, `<file2>`, ...
- **tests added**: `<test_file>` (+N cases). Total: <before> -> <after>
- **behavior implemented**: <one-paragraph factual summary>
- **design decisions (deviations from PLAN)**:
  - `<short title>`: <what was different and WHY>. Visible in:
    `<path:line>`. Impact on next milestone: <e.g., "must respect new
    invariant X">.
  - (none) if truly no divergences
- **known limitations**:
  - <thing not fully done; e.g., "happy-path only, error case deferred">
  - (none) if you fully cleaned up

Prior subsections are NEVER deleted or rewritten — each milestone is the
source of truth on itself.
-->

## 3. Current repo state

> Re-verify these numbers before starting work.

- **last commit**: `8f1d98f` — `git -C python-replica show 8f1d98f`
- **tests**: 615 passing
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
  additively); every existing test in `tests/test_compact.py` that
  assumes `RuleBasedSummarizer` default behaviour MUST continue
  passing when `provider=None` (M1 adds new test cases for the
  `provider=MockProvider(...)` branch).
- **compatibility requirements**:
  - `ContextCompactor`'s existing `compact_threshold` ratio parameter
    must be preserved as a SECOND legacy trigger alongside the new
    double-headroom formula (M1 exit gate). The aggressive preset
    relies on lowering `compact_threshold`.
  - `_remove_orphan_tool_results()` in `context.py` stays in place
    as defence-in-depth even after M2 makes snip the primary orphan
    handler.

## 5. Next milestone guidance

For `M1` — compact-thresholds-and-llm-default:

- **next scope**: see `initiatives/current/PLAN.md` and
  `initiatives/current/config.yaml` for the authoritative scope.
  Three additive deltas in `compact.py`: (a) microcompact gains
  `keep_recent: int = 5`; (b) ContextCompactor.should_compact() gains
  the double-headroom formula + min_session_tokens floor while
  preserving the legacy compact_threshold path; (c) ContextCompactor
  gains a `provider` kwarg that selects LLMSummarizer as default.
- **relevant files**:
  - `src/simple_coding_agent/compact.py` — primary edit target
    (MicroCompactor + ContextCompactor constructors and method
    signatures)
  - `src/simple_coding_agent/cli.py` — add four CLI flags
    (`--microcompact-keep-recent`, `--output-headroom`,
    `--compact-headroom`, `--min-session-tokens`) wired through
    existing `_resolve_threshold` precedence (explicit > aggressive
    preset > built-in default)
- **expected tests**:
  - extend `tests/test_compact.py` with:
    - microcompact preserves 5 latest compactable tool_results per
      (tool, path)
    - should_compact fires by new formula (mock context_window /
      tokens), respects min_session_tokens floor
    - should_compact still fires by legacy compact_threshold path
    - ContextCompactor with `provider=MockProvider(...)` uses
      LLMSummarizer; with `provider=None` still uses
      RuleBasedSummarizer
- **risks**: M1 has no prior-milestone risks to inherit. Watch for:
  - existing `cli.py` aggressive preset must keep lowering all three
    new thresholds when `--aggressive-thresholds` is set; otherwise
    `examples/visibility_full_demo.py` and `examples/stress_demo.py`
    will stop firing compaction.
  - Backward-compatibility test sweep: run `pytest --tb=no -q`
    after every change; any regression in `tests/test_compact.py`,
    `tests/test_stress_full_compact.py`, or
    `tests/test_microcompact_runtime.py` means the back-compat
    strategy in the exit gate hasn't held.

The full ready-to-run prompt is at:
`initiatives/current/prompts/M1.md`

The autonomous loop (`automation/scripts/run_all_milestones.sh`) reads
that prompt file directly. This Section 5 exists for manual
single-milestone restarts via `automation/scripts/run_next.sh`.
