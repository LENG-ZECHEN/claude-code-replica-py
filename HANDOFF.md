# HANDOFF — Next: M3

> Updated by: M2 session
> Date: 2026-05-21
> Read this file FIRST in the next session, then verify against git/pytest.

---

## 1. Objective State

> The next session MUST re-verify these numbers. Do not trust this list
> blindly — re-run the commands.

- Last commit: subject prefix is `P9-M2:` — `git -C python-replica log --oneline -1` to read the hash; `git -C python-replica show HEAD` to inspect contents
- pytest: 436 passing (was 421 after M1 + 9 untracked tests already on disk, delta +15 from M1 baseline)
- mypy:   clean (Success: no issues found in 17 source files)
- ruff:   clean (All checks passed!)
- Branch: main

## 2. What M2 Accomplished

- C1: `examples/stress_demo.py` — drives full-compact (210k-char scripted
  transcript, 10k-token `ContextBudget`, `keep_recent=4`,
  `compact_threshold=0.5`) and reactive-compact
  (`PromptTooLongError` → retry). Prints the normative markers
  `compact fired (messages_summarized=N)` and
  `reactive compact fired (messages_summarized=N)` on separate lines so
  the closing `)` is exact per RUNTIME_ACTIVATION_PLAN.md section 4.
- C2: `examples/microcompact_demo.py` — seeds 120-min-aged assistant
  timestamps; a `_CallCountingMicroCompactor` wraps `MicroCompactor` and
  reports `microcompact fired (results cleared=N)`. `--fresh` flips to
  current timestamps and produces `microcompact skipped` (negative path).
- Tests 3.3 (section 3.3 of the plan): `tests/test_stress_full_compact.py`
  (6 cases — full compact, reactive compact x2, total-budget
  externalization x2, snip-on-repeated-read) and
  `tests/test_microcompact_runtime.py` (3 cases — fires-when-aged,
  runs-at-most-once-per-loop, skipped-when-fresh) were already on disk as
  untracked files from the prior M1 session; M2 lands them with the
  demos.
- Demo-stdout tests: `tests/test_stress_demo.py` (3 cases) and
  `tests/test_microcompact_demo.py` (3 cases) verify the exit-gate
  markers reach stdout via `capsys`.
- `.gitignore` adds `logs/` so the autonomous-loop's runtime log dir no
  longer dirties `git status` after each milestone run.
- pytest 421 → 436 (delta +15: 9 from already-on-disk section-3.3 tests
  + 6 from the new demo tests). Exit gate target was ≥435; we are 1 over.

## 3. Decisions Made That Diverge From Plan ⚠️

> THE MOST IMPORTANT SECTION. Any place reality diverged from
> RUNTIME_ACTIVATION_PLAN.md — alternative library, skipped test,
> renamed function, added abstraction, deferred work, etc. Include
> the WHY so the next session can decide whether to inherit or revert.

- **Section 3.3 test files were on disk before M2 started.** When this M2
  session began, `tests/test_stress_full_compact.py` and
  `tests/test_microcompact_runtime.py` were already present as untracked
  files (left by a prior abandoned attempt). pytest baseline showed 430,
  not the 421 documented in M1's handoff. M2 inherited those files as-is
  (after one ruff auto-fix for import sorting) rather than rewriting
  them. They match section 3.3 of the plan and pass cleanly, so the
  inheritance is benign. The 6-case count in `test_stress_full_compact.py`
  is one over the 5 listed in the plan because a
  `test_tool_result_total_budget_externalizes_largest_first` was added
  to assert largest-first ordering of the total-budget cap.
- **Marker line is split into two lines.** The plan's normative marker is
  literally `compact fired (messages_summarized=N)` — a single closing
  paren immediately after the integer. The first draft of the demo
  emitted the full detail inside the same parentheses
  (`...=N, pre_tokens=X, post_tokens=Y)`), which broke the simplest
  regex match. The demo now emits the exact marker on one line and the
  pre/post token detail on a `[detail]` line beneath. Tests assert the
  exact form.
- **`examples/microcompact_demo.py` does not monkeypatch `datetime.now`.**
  The plan's wording was "backdated timestamps + monkeypatched
  `datetime`", but the demo runs in its own process; subtracting
  `timedelta(minutes=120)` from `datetime.now(UTC)` is enough to age the
  timestamps relative to "now" without any monkeypatching. The
  monkeypatched-`datetime` flavor is only used in
  `tests/test_microcompact_runtime.py`, where it pins time inside the
  `compact` module so the assertion isn't sensitive to test-wall-clock
  drift. This keeps the demo dependency-free for users running it
  directly.
- **`logs/` is now gitignored.** The autonomous-loop driver
  (`scripts/run_all_milestones.sh`) writes `logs/M{N}.log` and
  `logs/loop.log` each run. Without this, every milestone session would
  start with a dirty working tree from the previous run's tail logs.
  Subsequent milestones should not need to re-add this.

## 4. Open Questions / Blockers for M3

> Anything needing human input, or pre-conditions for M3.
> If none, write "(none)".

- (none) — all M2 quality gates green, demos run cleanly with
  `python examples/stress_demo.py` and `python examples/microcompact_demo.py`,
  and the working tree is clean (modulo the gitignored `logs/`).

## 5. Next Session Prompt

> Paste the content of the fenced block below into a fresh `claude`
> session opened from `python-replica/`. The prompt is self-contained;
> the next session needs nothing from the current conversation.

```
I'm continuing work on simple_coding_agent, a Python replica of Claude
Code v2.1.88's context-management and memory pipeline.

Before doing anything:
1. Read CLAUDE.md (architecture + completed P-roadmap).
2. Read RUNTIME_ACTIVATION_PLAN.md
     - Section 4 for milestone M3's scope
     - Section 5 for execution rules
3. Read HANDOFF.md — pay close attention to Section 3
   "Decisions Made That Diverge From Plan".
4. Run `git log --oneline -10` and `pytest --tb=no -q` to confirm
   the baseline matches HANDOFF.md Section 1.

Then execute Milestone M3 only:
  - C3 + C4 + B3   (from RUNTIME_ACTIVATION_PLAN.md Section 2)

Follow Section 5 "Execution Rules" in RUNTIME_ACTIVATION_PLAN.md
strictly. The exact test case lists are in plan Section 3.3 (metrics) +
Section 3.2 (session-persist).

Out of scope: any other milestone. Do NOT touch out-of-milestone code.

Exit ritual for this session (MANDATORY — do all five before stopping):
  1. Milestone M3's exit gate (per plan Section 4) is met.
  2. `git commit -m "P9-M3: <one-line>"` has landed.
  3. CLAUDE.md updated with a P9-M3 entry mirroring P1-P8 format.
  4. PROGRESS.md appended with a one-line summary
     (create the file if it does not exist yet).
  5. HANDOFF.md overwritten using templates/handoff_template.md, with
     all placeholders filled, to hand off to the M4 session.

Confirm you've read all three files (CLAUDE.md, RUNTIME_ACTIVATION_PLAN.md,
HANDOFF.md), then proceed directly to TDD.
```
