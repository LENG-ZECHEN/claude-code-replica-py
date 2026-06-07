# REVIEW — plan-surface

## Summary

- Initiative period: 2026-06-08 → 2026-06-08
- Milestones: 3, all complete
- pytest: 835 → 904 (delta +69; including +5 new tests added during review-fix)
- mypy: clean (no issues found in 30 source files)
- ruff: clean (All checks passed!)
- Total milestone commits before review: 3 (M1 `e62e928`, M2 `75eac7c`, M3 `edd25d0`)
- Review-time commits: 2 (`4efc445` review-fix, `1e242b5` review-doc)
- Final pre-review commit: `edd25d0`
- Final pre-wrap commit after review repairs: `1e242b5`
- Wrap commit: pending until Phase 2C
- Review mode: multi-agent staged review + main-agent repair loop
  (`code-reviewer` + `doc-curator-candidate-finder` in parallel,
  reconciled by main agent, repaired by main agent, then `demo-narrator`)

## Lessons learned

- **The 5-bullet mandatory-reading forcing function paid off.** All three
  milestone prompts scored 40/40 on prompt quality; agents executing
  M1–M3 referenced specific TS source line ranges in their commit
  messages, suggesting the mandatory-reading discipline reached the
  fact-quality of the diff. Worth keeping for future initiatives.
- **Per-milestone "shipped vs deferred" enumerations prevent scope creep
  but do not prevent wiring oversights.** PLAN listed
  `--no-todo-reminder` / `--todo-reminder-turns` as wired on both REPLs,
  but M1 only touched `cli.py`. A "this flag must appear in `--help`
  output of both `simple-agent` and `simple-agent-openai`" exit-gate
  predicate would have caught it.
- **`exit-gate quote actual command output` should beat "Trust PROGRESS
  blocks".** M2's PROGRESS reported `ruff: clean` but M3's commit
  cleaned up 16 ruff errors M2 left behind. Phase 2A's exit gate runs
  pytest but takes mypy/ruff status on faith from the agent's report.
  Strengthening that check is a process-level follow-up.
- **The three-layer registration pattern works but is non-obvious.** The
  `build_default_registry` no-op → `AgentLoop._register_tools` rewire →
  `cli._build_repl_loop` re-rewire ladder is mechanically correct but
  takes minutes to learn for a new contributor. Codified as ADR-0004 to
  give future maintainers a fixed referent.
- **Counter splits need a wiring test, not just a metric test.** M3
  added `plan_mode_exits_approved` / `_rejected` but never wired the
  rejected path to a fire site, so the metric was structurally correct
  but operationally dead. A regression test that *runs* the rejection
  flow end-to-end (added in review-fix) catches this earlier than a
  unit test that just constructs the counter.

## Main-agent reconciliation note

- **Subagent agreement was high.** `code-reviewer` and
  `doc-curator-candidate-finder` did not contradict each other —
  doc-curator focused on documentation candidates and did not
  re-litigate code findings; code-reviewer surfaced one document-claim
  risk (HANDOFF describing both rejection counters as live) but
  phrased it as a code risk rather than a doc-edit proposal.
- **Findings selected for review-time repair:** 4 (one HIGH, two
  MEDIUM, one LOW). All deemed safe and scoped: each touches a single
  feature surface, has clear tests-first invariants, and required no
  cross-cutting refactor.
- **Findings deferred:** 5 (all LOW + one MEDIUM that is purely
  historical). Reasons documented in the "Deferred findings"
  subsection.
- **Tier A/B doc decisions:** Every Tier A and Tier B candidate from
  doc-curator was applied — 4 CLAUDE.md per-file summary appends, 1
  README.md flag-paragraph append, 2 subsystem docs (`docs/todo.md`,
  `docs/plan-mode.md`), 1 ADR (`ADR-0004`), and the ADR-index row.
  Tier C candidates 1 and 2 (CLAUDE.md trace.py channel count from 9
  to 11; CLAUDE.md models.py MessageType list expansion) were
  applied because they remove information made stale by this
  initiative and meet the "small, local, mechanical" criteria. Tier C
  candidates 3 and 4 (README.md slash-command section creation,
  CLAUDE.md Current Limitations Plan Mode addendum) were deferred —
  both involve subjective placement decisions that benefit from
  human review.
- **Owner-brief inclusion:** All HIGH and MEDIUM findings included.
  LOW findings included only where they have practical impact on
  telemetry interpretation (the `record_plan_mode_exit` conflation
  issue is included because it directly affects the new metric).

### Prompt quality scorecards (from code-reviewer)

| Milestone | Clarity | Completeness | Scope alignment | Constraint specificity | Exit-ritual correctness | Out-of-scope enumeration | Mandatory reading completeness | Exit gate objectivity | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M2 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M3 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |

All three prompts are exemplary — verbatim exit gates, comprehensive
source-mapping, explicit out-of-scope lists, mandatory reading order
with the 5-bullet-summary forcing function, and the 6-check exit
verification surface.

### Execution quality scorecards (from code-reviewer)

| Milestone | Commit hygiene | Test growth | Gate honor | Divergence discipline | Log cleanliness | Implementation matches PLAN | Scope discipline | HANDOFF accuracy | Failure-path coverage | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 4 | 5 | 4 | 4 | 4 | 4 | 40/45 |
| M2 | 5 | 5 | 3 | 4 | 5 | 4 | 5 | 4 | 5 | 40/45 |
| M3 | 5 | 5 | 5 | 4 | 5 | 4 | 5 | 4 | 4 | 41/45 |

Per-row docking explained inline in the code-reviewer output below.

- **M1 — Divergence/Implementation/Scope (4 each)**: 3 deviations from
  PLAN (counter-based timing vs transcript scanning, registration
  pathway, provider.py touch) — all valid choices but one
  (`--no-todo-reminder` / `--todo-reminder-turns` not wired into
  openai_cli) was a true gap, fixed in review-fix `4efc445`.
- **M1 — HANDOFF accuracy / Failure-path coverage (4)**: M1 PROGRESS
  block omitted the `- commit: [plan-srf/M1]` line specified by the
  template. Failure-path tests were thinner than ideal.
- **M2 — Gate honor (3)**: M2's PROGRESS claimed `ruff: clean` but
  M2's commit shipped 16 unused-import errors that M3 cleaned up.
  This is a Gate-honor failure even though pytest stayed green.
- **M2 — Divergence/Implementation (4)**: soft-deny message dropped
  the PLAN-spec recovery hint (fixed in review-fix `4efc445`);
  `_set_permission_mode` source kwarg was deferred to M3 with a
  HANDOFF note (acceptable).
- **M3 — Implementation matches PLAN (4)**: `plan_mode_exits_rejected`
  counter was structurally added but operationally dead (fixed in
  review-fix `4efc445`); `record_plan_mode_exit` conflates slash and
  tool-approved exits (deferred — needs semantic decision).
- **M3 — HANDOFF accuracy (4)**: HANDOFF advertised both counters as
  live, but `_rejected` was dead until review-fix.
- **M3 — Failure-path coverage (4)**: rejection-path tests covered
  the raising behavior but not the metric-bump invariant
  (rectified — review-fix adds the bump test).

## Findings and repair ledger

### Fixed during review

- **`plan_mode_exits_rejected` was dead code** — Tier A — severity HIGH
  - Source: code-reviewer detail finding
  - Fix commit: `4efc445 [plan-srf/review-fix]`
  - Files changed: `src/simple_coding_agent/plan_mode_tools.py`,
    `src/simple_coding_agent/loop.py`,
    `src/simple_coding_agent/cli.py`
  - Tests added: `tests/test_exit_plan_mode.py` — 3 new cases:
    `test_exit_plan_mode_rejection_bumps_metrics_when_supplied`,
    `test_exit_plan_mode_rejection_without_metrics_does_not_crash`,
    `test_exit_plan_mode_approval_does_not_double_bump_rejected`.
  - Validation: `pytest tests/test_exit_plan_mode.py -q` → 11
    passed; full `pytest --tb=no -q` → 904 passed + 1 xpassed.

- **Soft-deny message lost PLAN-spec recovery guidance** — Tier B — severity MEDIUM
  - Source: code-reviewer detail finding
  - Fix commit: `4efc445 [plan-srf/review-fix]`
  - Files changed: `src/simple_coding_agent/loop.py:885-892`
  - Tests added: none (existing assertions
    `"'write_file' is not allowed"` etc. still pass)
  - Validation: `pytest tests/test_plan_mode_soft_deny.py -q` → 9
    passed.

- **`--no-todo-reminder` / `--todo-reminder-turns` not wired into
  openai_cli** — Tier B — severity MEDIUM
  - Source: code-reviewer detail finding
  - Fix commit: `4efc445 [plan-srf/review-fix]`
  - Files changed: `src/simple_coding_agent/openai_cli.py`
  - Tests added: `tests/test_openai_cli_repl.py` — 2 new cases:
    `test_openai_repl_no_todo_reminder_disables_machinery`,
    `test_openai_repl_todo_reminder_turns_propagates`.
  - Validation: `pytest tests/test_openai_cli_repl.py -q` → 10
    passed.

- **`transcript.normalize_for_api` filter list out of sync with
  `compact.py`** — Tier B — severity LOW
  - Source: code-reviewer detail finding
  - Fix commit: `4efc445 [plan-srf/review-fix]`
  - Files changed: `src/simple_coding_agent/transcript.py:104-112`
  - Tests added: none (no existing test depended on the incomplete
    list; the change is purely defensive)
  - Validation: `pytest tests/test_transcript.py -q` → 14 passed.

### Deferred findings / follow-ups

- **`_todo_nudge` re-prepended on every inner agent turn** — Tier C —
  severity LOW
  - Why deferred: behavior is correct; only token-inefficient under
    heavy multi-tool inner-turn budgets. Fix requires cache-invalidation
    analysis to avoid breaking prompt-prefix stability.
  - Suggested next step: clear `_todo_nudge` after the first successful
    `build()` call inside the outer `for turn in range(_max_steps)`
    loop in both `AgentLoop.run()` and `run_stream()`.

- **`record_plan_mode_exit` conflates slash-toggle exits with
  tool-approved exits** — Tier C — severity LOW
  - Why deferred: distinction is a semantic choice (whether `/plan`
    user-driven exits are "the same as" model-driven tool exits).
    Subjective enough to leave to product judgment.
  - Suggested next step: add `_manual` vs `_approved` separation,
    plumb `source` from `_set_permission_mode` into the counter
    dispatch.

- **`_set_permission_mode(PLAN)` is non-idempotent on entry metric** —
  Tier C — severity LOW
  - Why deferred: low impact; only matters under model spam-calls of
    `enter_plan_mode`. Easy to fix later when telemetry surfaces a
    spike.
  - Suggested next step: `if self._permission_mode == mode: return`
    early guard at top of `_set_permission_mode`.

- **`count_assistant_turns_since` + `_is_*` predicates exported but
  never called in production** — Tier C — severity LOW
  - Why deferred: the helpers exist as parity tests against the TS
    transcript-scanning approach; removing them loses source-mapping
    documentation, but leaving them creates the impression they are
    live.
  - Suggested next step: either remove from `__all__` with a
    "kept for forward-compat parity test only" docstring note, or
    wire as an alternate arm-logic mode behind a kwarg.

- **M1 PROGRESS block omitted `- commit: [plan-srf/M1]` template
  line** — historical, severity LOW
  - Why deferred: would require git-history rewrite.
  - Suggested next step: lint that PROGRESS.md milestone heading is
    followed by a commit-line in Phase 2A exit gate.

- **M2 shipped 16 ruff errors despite PROGRESS claiming
  `ruff: clean`** — historical, severity MEDIUM
  - Why deferred: M3 already fixed the symptom.
  - Suggested next step: change Phase 2A exit gate to capture
    `ruff check .` stdout into the milestone log instead of trusting
    agent-reported status.

## Auto-applied edits

| Tier | Target | Summary | Trigger | Source |
|---|---|---|---|---|
| A | `CLAUDE.md` | Appended `### todo.py` per-file summary section | new `.py` file with public symbols | doc-curator |
| A | `CLAUDE.md` | Appended `### todo_tool.py` per-file summary section | new `.py` file with public symbols | doc-curator |
| A | `CLAUDE.md` | Appended `### permission.py` per-file summary section | new `.py` file with public symbols | doc-curator |
| A | `CLAUDE.md` | Appended `### plan_mode_tools.py` per-file summary section (includes review-fix `metrics=` kwarg note) | new `.py` file with public symbols | doc-curator + main-agent (kwarg note) |
| A | `README.md` | Appended new paragraph documenting `--no-todo-reminder` / `--todo-reminder-turns` | new CLI flag on existing entry-point | doc-curator |
| B | `docs/todo.md` | Created subsystem doc for TodoWrite V1 | new module >150 LOC with ≥3 public symbols | doc-curator |
| B | `docs/plan-mode.md` | Created subsystem doc for Plan Mode | cross-cutting subsystem reach across 9+ src files | doc-curator |
| B | `docs/DECISIONS/0004-noop-default-tool-factory-then-loop-rewires.md` | Created ADR-0004 for three-layer registration pattern | architectural divergence across 4 source files | doc-curator |
| B | `docs/DECISIONS/README.md` | Appended ADR-0004 row to index | new ADR file created | doc-curator |
| C | `CLAUDE.md` (trace.py summary) | Updated `frozen at 9 names` to `frozen at 11 names` + added `todo` / `permission` channels | small mechanical accuracy fix caused by this initiative | doc-curator |
| C | `CLAUDE.md` (models.py summary) | Updated `MessageType` enumeration to include `ATTACHMENT_MEMORY`, `ATTACHMENT_TODO_NUDGE`, `ATTACHMENT_PLAN_MODE`, `SNIP_BOUNDARY` | small mechanical accuracy fix | doc-curator |

## Proposed edits (need human review)

1. `README.md` — add a `/todos` and `/plan` row to a documented
   REPL slash command surface. The README currently lists slash
   commands only in `_REPL_HELP_TEXT`. Trigger: README.md needs new
   content category. Subjective placement decision (new section vs.
   inline interleaving), so left for human judgment.
2. `CLAUDE.md` Current Limitations — append Plan Mode entries
   (attachment + soft-deny enforcement model; plan persistence /
   allowedPrompts / reentry attachments out of scope;
   `_confirm_exit_plan` blocks event loop in `--stream` mode).
   Trigger: new theme being added to a thematically-grouped list.
   Subjective whether to introduce a new theme or interleave with
   existing bullets — left for human judgment.

## Validation results

Initial quality gates (before review-fix):
- pytest: 899 passed + 1 xpassed
- mypy: clean
- ruff: clean

Targeted tests run during review-fix:
- `pytest tests/test_exit_plan_mode.py tests/test_plan_mode_soft_deny.py
  tests/test_transcript.py tests/test_repl_plan_mode.py -q` → 44 passed
  (after wiring `metrics=` kwarg, before openai_cli flag wiring)
- `pytest tests/test_openai_cli_repl.py tests/test_exit_plan_mode.py
  tests/test_plan_mode_soft_deny.py tests/test_transcript.py
  tests/test_repl_plan_mode.py -q` → 61 passed (after openai_cli flag
  wiring + 2 new flag tests)

Final quality gates (after review-fix + review-doc):
- pytest: 904 passed + 1 xpassed
- mypy: Success: no issues found in 30 source files
- ruff: All checks passed!
- `git status --short`: clean

One transient ruff error during review-fix (quoted forward reference
to `MetricsCollector` despite `from __future__ import annotations`)
was fixed in the same `4efc445` commit by removing the quotes.

## Phase 2C: Wrap-up actions taken

(Filled in after Phase 2C runs.)

## Owner brief

The decision-maker-facing Chinese owner brief lives in
[`OWNER_BRIEF.zh-CN.md`](./OWNER_BRIEF.zh-CN.md). Read that file for
"what was built / how to demo it / before-after / how to talk about it".
