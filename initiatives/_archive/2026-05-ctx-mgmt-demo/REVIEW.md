# REVIEW — ctx-mgmt-demo

## Summary

- Initiative period: 2026-05-25 -> 2026-05-25
- Milestones: 3 (M1, M2, M3), all complete
- pytest: 816 -> 820 (delta +4 — M1 +3, review-fix regression test +1)
- mypy: clean (no issues in 26 source files)
- ruff: clean — `ruff check src tests` AND repo-wide `ruff check .` both green
  (the latter was 10 errors at M3; fixed during review)
- Total non-review commits before review: 5 (`bootstrap` + M1 + M2×2 + M3)
- Review-time commits: 3 (`8ef0a4f`, `a6049ce` review-fix; `f937d8f` review-doc)
- Commits in `9ba662b..HEAD`: 8
- Final pre-review commit: `7c7496c` (`[ctx-demo/M3]`)
- Final pre-wrap commit after review repairs: `f937d8f`
- Wrap commit: pending (this archive's final `[ctx-demo/wrap]` commit — see `logs/review.log`)
- Review mode: multi-agent staged review + main-agent repair loop
  (`code-reviewer` + `doc-curator-candidate-finder` in parallel,
  reconciled by main agent, repaired by main agent, then `demo-narrator`)

## Lessons learned

- **A "ruff: clean" milestone claim must run the same scope the wrap gate runs.**
  M2 reported clean after `ruff check src tests`, but the repo-wide `ruff check .`
  (which the wrap pre-flight effectively cares about) had 10 errors in the new
  `demo/_scripts/capture_scenario.py`. Future milestone prompts that touch files
  outside `src/`+`tests/` should pin the exact ruff scope in the exit gate.
- **A "wired but inert" metric is a real bug, not bookkeeping.** The
  `tool_result_store` was passed to `ContextBuilder` but not `AgentLoop`, so
  `/stats externalized_bytes` was 0 for every REPL session. The milestone agent
  noticed the symptom and chose a private-attribute workaround in the demo driver
  instead of the 1-line product fix. HANDOFF §5 correctly flagged it for review,
  and the review applied the real fix + a regression test. Self-flagging in
  HANDOFF §5 is exactly the behavior that made this cheap to fix.
- **Verbatim exit-gate headers belong inline in the prompt.** M2 needed a second
  `[ctx-demo/M2]` commit (`7ef509b`) only to rename a HANDOFF section to the
  harness-required verbatim header `## 5. Next milestone guidance`. Inlining the
  five exact section titles in the prompt §5 would have prevented the split commit.
- **Side-effect / docs milestones still ship untested logic.** M2's 200-LOC
  capture driver shipped with zero tests; a thin smoke test of `_metrics_to_dict`
  / `_render_transcript` would have caught the kind of drift the workaround masked.
- **Immutable artifacts + a mutable reproducer need an explicit provenance note.**
  Fixing the wiring bug made the canonical `_artifacts/` (captured pre-fix) diverge
  from a fresh run; the honest fix was a one-paragraph note in notebook 01, not
  re-capturing (which would spend API and is out of scope).

## Main-agent reconciliation note

**Conflicts:** none material. `code-reviewer` and `doc-curator-candidate-finder`
were complementary, not contradictory. Both independently surfaced CLAUDE.md
staleness, but on **different lines**: the doc-curator flagged the `compact.py`
summary's hardcoded "60 minutes" (Tier C), while code-reviewer flagged the
`loop.py` summary's "at most once per loop instance" (a separate stale phrase).
I treated these as two distinct doc items.

**Severity adjustments:** none. The wiring bug was kept at MEDIUM (it silently
under-reports a real mechanism on both production CLI surfaces, but does not lose
data — externalization itself works). The ruff/false-clean and private-internals
findings were kept at LOW.

**Selected for review-time repair:** (1) wiring bug — fixed + regression test;
(2) ruff 10 violations — fixed; (3) private-internals `_store` reach — removed as
a consequence of (1); (4) notebook 01 staleness ripple from (1) — synced;
(5) Tier A README flag append — applied; (6) Tier C CLAUDE.md "60 minutes"
precision — applied (small, removes info made stale by M1).

**Deferred (recorded as follow-ups / proposals):** the "at most once per loop
instance" CLAUDE.md staleness (pre-existing since the P9 REPL; one of the two
occurrences sits in the protected Implementation Roadmap section, so a consistent
fix needs human judgment) and the M2 PROGRESS scenario-01 counter under-report
(append-only committed file; not rewritten).

**Doc-tier decisions:** Tier A README append — APPLIED. Tier B — none (ADR
threshold correctly not met: no new module/subdir, no architectural divergence,
no single divergence touching >2 src files). Tier C "60 minutes" — APPLIED (Step
3D small-safe-stale criteria). Tier C "at most once" + roadmap bullet — PROPOSED
only.

**Owner-brief selection:** included the wiring bug (MEDIUM) framed as fixed, and
the microcompact `invocations≠clears` LOW (it is easy to misread). Excluded
bookkeeping noise (PROGRESS counter gap) from the headline findings, recorded it
under "还需要补什么".

### Reconciled prompt quality scorecards (source: code-reviewer)

| Milestone | Clarity | Completeness | Scope alignment | Constraint specificity | Exit-ritual correctness | Out-of-scope enumeration | Mandatory reading completeness | Exit gate objectivity | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M2 | 5 | 5 | 5 | 5 | 4 | 5 | 5 | 5 | 39/40 |
| M3 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |

- **M2 Exit-ritual correctness (4/5)**: §5 referenced the 5-section HANDOFF
  template but did not inline the harness-enforced verbatim headers, so M2's first
  commit titled a section differently, failed exit-gate check 5, and forced a
  second `[ctx-demo/M2]` commit (`7ef509b`) just to rename the header.

### Reconciled execution quality scorecards (source: code-reviewer)

| Milestone | Commit hygiene | Test growth | Gate honor | Divergence discipline | Log cleanliness | Implementation matches PLAN | Scope discipline | HANDOFF accuracy | Failure-path coverage | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M2 | 4 | 3 | 3 | 5 | 5 | 5 | 5 | 4 | 3 | 37/45 |
| M3 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 4 | 5 | 44/45 |

- **M2 — 37/45**: Commit hygiene 4 (two `[ctx-demo/M2]` commits vs one prompted);
  Test growth 3 / Failure-path coverage 3 (200-LOC driver shipped untested — defensible
  for a side-effect milestone, but thin); Gate honor 3 (reported "ruff: clean" while
  the M2 commit introduced 10 repo-wide ruff errors); HANDOFF accuracy 4 (PROGRESS M2
  block omits that scenario 01 also fired `full_compacts=2` / `microcompact=1`).
- **M3 — 44/45**: HANDOFF accuracy 4 (framed the M2-introduced ruff errors as
  "pre-existing", soft-pedaling that they were introduced within this initiative and
  falsely reported clean at M2; the notebook prose itself is accurate).

## Findings and repair ledger

### Fixed during review

- **`tool_result_store` not wired into REPL `AgentLoop`** — Tier B — severity MEDIUM
  - Source: code-reviewer + HANDOFF §5 (main agent confirmed against `cli.py:459/499/505`, `loop.py:136/172/655`)
  - Fix commit: `8ef0a4f [ctx-demo/review-fix] wire tool_result_store into _build_repl_loop`
  - Files changed: `src/simple_coding_agent/cli.py` (+1 line in `loop_kwargs`), `tests/test_repl.py` (+1 regression test)
  - Tests added: `tests/test_repl.py::test_build_repl_loop_wires_tool_result_store_into_agent_loop`
  - Validation: targeted test PASS; would have failed pre-fix (no key in `loop_kwargs` → `AgentLoop._tool_result_store is None` → first assert fails). Full pytest 819 -> 820, mypy clean, ruff `src tests` clean.

- **`capture_scenario.py` ruff violations + false "ruff: clean" claim** — Tier C/gate-honesty — severity LOW
  - Source: code-reviewer (confirmed: `ruff check .` = E402×5, I001, E501×4, all in this one file)
  - Fix commit: `a6049ce [ctx-demo/review-fix] clean up M2 capture driver + sync notebook 01`
  - Files changed: `demo/_scripts/capture_scenario.py`
  - Tests added: none (formatting only; string values preserved byte-identically via implicit concatenation, verified)
  - Validation: `ruff check .` now clean; `py_compile` OK; pytest 820.

- **Capture driver reached into `loop._context_builder._store` (private)** — Tier B — severity LOW
  - Source: code-reviewer; resolved as a consequence of the wiring fix
  - Fix commit: `a6049ce` (removed the `externalized_bytes` workaround; `_metrics` now carries the real value)
  - Files changed: `demo/_scripts/capture_scenario.py`
  - Validation: `py_compile` OK; the remaining `loop._transcript` / `loop._metrics` reads are pragmatic demo-only access (LOW, left as-is).

- **Notebook 01 described the wiring bug + workaround as current** — Tier C (review-ripple) — severity LOW
  - Source: main-agent inspection (consequence of the wiring fix)
  - Fix commit: `a6049ce`
  - Files changed: `demo/01_tool_result_management.md` (note block + "What to look for" row)
  - Validation: now states the bug was fixed during review and the canonical artifacts predate the fix.

### Deferred findings / follow-ups

- **CLAUDE.md "at most once per loop instance" is stale** — Tier C — severity LOW
  - Why deferred: pre-existing (became inaccurate at the P9 REPL, not caused by this
    initiative); the phrase appears both in the `loop.py` per-file summary (line 15)
    and the protected Implementation Roadmap P5 bullet (line 73). RUNBOOK forbids
    auto-editing the Roadmap, and fixing only one occurrence would leave them
    inconsistent. Recorded as a Proposed edit below.
  - Suggested next step: human reconciles both lines to "at most once per distinct
    latest-assistant message" (the actual `_microcompacted_against_assistant_uuid`
    guard at `loop.py:619-626`; notebook 03's `microcompact_invocations=3` confirms it).

- **PROGRESS M2 block under-reports scenario-01 counters** — Tier C — severity LOW
  - Why deferred: PROGRESS.md is an append-only, already-committed fact log; the
    notebook (the published surface) already documents the double compaction.
  - Suggested next step: if PROGRESS is ever revised, note the incidental
    `full_compacts=2` / `microcompact_invocations=1` for scenario 01.

## Auto-applied edits

- Tier A | `README.md` | append `--microcompact-minutes` (both CLIs) + `--max-turns` (openai REPL) to the REPL flag list | trigger: Tier A "a new CLI flag added to an existing entry-point CLI (visible in `--help`)" | source: doc-curator candidate (HIGH) — applied in `f937d8f`
- Tier C | `CLAUDE.md` | `compact.py` summary "older than 60 minutes" -> "`threshold_minutes` (default 60, overridable via `--microcompact-minutes`; 0 = any age)" | trigger: per-file summary made stale by M1's new flag (Step 3D small/safe/stale criteria) | source: doc-curator candidate — applied in `f937d8f`
- Tier B | (none) | ADR threshold not met: no new module/subdir, no architectural divergence keyword, no single divergence touching >2 src files | source: doc-curator analysis

## Proposed edits (need human review)

1. `CLAUDE.md:15` (and `CLAUDE.md:73`, protected Roadmap) — reconcile "at most once per loop instance" to match the actual per-assistant-UUID guard — why: stale since the P9 REPL made one loop instance span turns; contradicts shipped notebook 03. Trigger: Tier C "an existing CLAUDE.md per-file summary needs paraphrasing".
   Suggested diff:
   ```diff
   - microcompact (cold cache cleanup, at most once per loop instance) -> snip redundant tool results
   + microcompact (cold cache cleanup, at most once per distinct latest-assistant message) -> snip redundant tool results
   ```
   (and, in the protected Roadmap P5 bullet, the same "at most once per loop instance" -> "at most once per distinct latest-assistant message").

2. `CLAUDE.md` "Implementation Roadmap" — optionally add a `ctx-mgmt-demo` roadmap bullet for consistency with every prior initiative — why: the Roadmap documents each initiative, and omitting this one is inconsistent. Trigger: Tier C; the Roadmap section is protected from auto-edit by the RUNBOOK, so this is a human decision.
   Suggested bullet (for human placement):
   ```markdown
   - **ctx-mgmt-demo initiative — M1–M3** (`cda6f2b`–`7c7496c`, review `8ef0a4f`–`f937d8f`, 2026-05-25). Two additive CLI flags (`--microcompact-minutes` on both REPLs; `--max-turns` on the openai REPL) plus real-DashScope (`qwen3.6-plus`) per-mechanism demo artifacts and three notebooks under `demo/`. Review fixed the `_build_repl_loop` `tool_result_store` wiring bug (`/stats externalized_bytes` was 0) + a regression test, and cleaned repo-wide ruff. pytest 816 -> 820, mypy + ruff clean.
   ```

## Validation results

- **Initial quality gate (Step 2, at M3 HEAD `7c7496c`)**: pytest 819 passed; mypy
  clean (26 files); `ruff check src tests` clean; `ruff check .` = **10 errors**
  (E402×5, I001, E501×4) all in `demo/_scripts/capture_scenario.py`. Classified as
  a safely-repairable initial gate failure -> entered review-and-repair mode.
- **Targeted tests for review repairs**:
  - `pytest tests/test_repl.py::test_build_repl_loop_wires_tool_result_store_into_agent_loop` -> 1 passed.
  - `py_compile demo/_scripts/capture_scenario.py` -> OK (script not runnable here without real API/credentials, by design).
- **Final validation gate (after repairs, HEAD `f937d8f`)**:
  - `pytest tests/ -q` -> **820 passed**
  - `mypy src/` -> clean (26 files)
  - `ruff check src tests` -> clean
  - `ruff check .` -> **clean** (whole-repo, was 10 errors)
  - `git status --short` -> clean (all repairs committed before Phase 2C)
- No failed command remained unresolved.

## Phase 2C: Wrap-up actions taken

- `git mv initiatives/current initiatives/_archive/2026-05-ctx-mgmt-demo`
- recreated empty `initiatives/current/` with `.gitkeep`
- rewrote `NOW.md` (no active initiative; last completed = ctx-mgmt-demo with final numbers)
- updated `initiatives/README.md` (moved the row Active -> Archived with final commit + period)
- wrote `initiatives/_archive/2026-05-ctx-mgmt-demo/logs/review.log`
- committed the archive as `[ctx-demo/wrap] post-execution review + archive (review-and-repair)`

## Owner brief

The decision-maker-facing Chinese owner brief lives in
[`OWNER_BRIEF.zh-CN.md`](./OWNER_BRIEF.zh-CN.md). Read that file for
"what was built / how to demo it / before-after / how to talk about it".
