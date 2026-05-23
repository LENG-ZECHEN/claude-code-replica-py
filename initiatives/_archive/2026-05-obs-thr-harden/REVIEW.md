# REVIEW — obs-thr-harden

## Summary

- **Initiative period**: 2026-05-23 → 2026-05-23
- **Milestones**: 3, all complete (M1, M2, M3)
- **pytest**: 557 → 615 (Δ +58; per-milestone: M1 557→584 +27, M2 584→605 +21, M3 605→615 +10)
- **mypy**: clean (21 source files); **ruff**: clean
- **Total commits in this initiative** (`e8e2206..HEAD`, excl. this wrap): 5
  — `6a5fe80` bootstrap, `6284ea8` M1, `4056370` M2, `9b00767` M3,
  `4582997` M3 SHA-fill.
- **Lessons learned**:
  - **What worked**: tight per-milestone touch surface (≤4 src + ≤4
    test) kept every session well below the 11-src/5-test water mark
    that thrashed the prior initiative's M1 at turn 243. All three logs
    are short and clean — no retries, no auto-compact loops. The PLAN's
    explicit "M1 must land before M3" ordering note and the pre-pinned
    `--help` wording (`preset value applies`) prevented the classic
    cross-milestone drift between a producer (M1's repr-quoting) and a
    consumer (M3's parser) and between a writer (M2's help text) and an
    asserter (M3's snapshot).
  - **What worked**: prompts carried PLAN's exact code sketches and the
    regression-scan command (`grep -rn "200_000\|8_192"`), so M2 fixed a
    user-visible default change without leaving broken tests for M3.
  - **Do differently next time**: the **self-referential SHA problem**
    bit two of three milestones. M1 and M2 recorded their commit SHA via
    `git commit --amend`, which re-hashes the commit, leaving the SHA
    written into PROGRESS/HANDOFF (`71d3c80`, `30945de`) pointing at the
    now-**unreachable pre-amend object** (verified: neither is an
    ancestor of HEAD). M3 solved it correctly with a *second* commit
    (`4582997`) that fills the SHA, keeping `9b00767` reachable. The
    milestone-prompt template / exit ritual should standardize on M3's
    two-commit approach (or omit the SHA from the bookkeeping files and
    cite "HEAD at commit time") so PROGRESS/HANDOFF SHAs stay reachable.
  - **Do differently next time**: M2's `--max-steps: default=None (if
    applicable — confirm during prompt)` left an ambiguity the agent had
    to resolve mid-run (it correctly found max-steps has no preset entry
    and kept default 10). Phase 1 should resolve "if applicable" hedges
    before the prompt ships.

## Phase 2B-3: Prompt quality scorecards

Scale 1–5 (5 best).

| Dimension | M1 | M2 | M3 |
|---|---|---|---|
| Clarity | 5 | 5 | 5 |
| Completeness (§1–§5 present + filled) | 5 | 5 | 5 |
| Scope alignment with PLAN | 5 | 5 | 5 |
| Constraint specificity (TDD / file-limit / no `-A`) | 5 | 4 | 5 |
| Exit-ritual correctness (§5 vs `milestone_prompt.md` §5) | 5 | 5 | 5 |
| Out-of-scope enumeration (§2.5 concrete) | 5 | 5 | 5 |
| Mandatory-reading completeness (§3) | 5 | 5 | 5 |
| Exit-gate objectivity | 5 | 5 | 4 |
| **Mean** | **5.0** | **4.875** | **4.875** |

Notes:
- **M2 constraint specificity 4**: `--max-steps: default=None (if
  applicable — confirm during prompt)` is the one non-specific
  instruction; everything else (sentinel logic, `_resolve_threshold`
  shape, regression-scan command, verbatim `--help` wording) is concrete.
- **M3 exit-gate objectivity 4**: the gate is objective overall, but the
  suggested `--help` assertion phrase `"Stream [trace]"` is not
  contiguous in the rendered help (a backtick splits it), which forced
  the executing agent to deviate to a whitespace-normalized match. The
  gate would have been more objective had it pinned the actually-rendered
  substring.
- §2.5 is present and concretely enumerated in all three prompts (other
  milestones, harness files, CLAUDE.md/README, `Tracer` Protocol,
  `NullTracer.emit` body, `_AGGRESSIVE_THRESHOLDS` keys, 9-channel list,
  new deps, broad-except). The four hard invariants from PLAN's "Anything
  else" are echoed in every prompt.
- §3 mandatory reading is complete per milestone-position: M1 lists 9
  reads (no prior git log needed); M2 adds `git log -10 + git show HEAD`
  and M1.log; M3 adds M1+M2 logs and the SHA-range lookup.

## Phase 2B-4: Execution quality scorecards

Scale 1–5 (5 best).

| Dimension | M1 | M2 | M3 |
|---|---|---|---|
| Commit hygiene | 5 | 5 | 4 |
| Test growth | 5 | 5 | 5 |
| Gate honor (mypy + ruff clean) | 5 | 5 | 5 |
| Divergence discipline | 5 | 5 | 5 |
| Log cleanliness | 5 | 5 | 5 |
| Implementation matches PLAN | 5 | 5 | 5 |
| Scope discipline | 5 | 5 | 5 |
| HANDOFF accuracy | 4 | 4 | 5 |
| Failure-path coverage | 5 | 5 | 5 |
| **Mean** | **4.89** | **4.89** | **4.89** |

Notes:
- **M3 commit hygiene 4**: M3 produced two commits (`9b00767` substantive
  + `4582997` SHA-fill) rather than the one-commit-per-milestone
  convention. This was the *correct* workaround (GateGuard hard-blocked
  `--amend`, and a second commit keeps `9b00767` reachable), and the
  second commit only touched SHA references in CLAUDE.md/HANDOFF/PROGRESS
  — within the bookkeeping allowlist, not scope-creep. Docked one point
  only to flag the convention deviation, not as a fault.
- **M1 / M2 HANDOFF accuracy 4**: the `commit:` field in HANDOFF Section
  2 and PROGRESS cites the pre-amend SHA (`71d3c80` for M1, `30945de`
  for M2). Both were verified **not ancestors of HEAD** — the reachable
  commits are `6284ea8` and `4056370`. The HANDOFF flags this as a known
  limitation ("the recorded sha is pre-amend; `git log -1` is
  authoritative"), so it is disclosed, not hidden — but the cited SHA is
  unreachable and will eventually be GC'd. See Proposed edit #1.
- **Scope discipline 5/5/5**: per-commit `--stat` confirms each milestone
  touched only its §2 "Expected files" plus the required bookkeeping
  (HANDOFF, PROGRESS, and — M3 only — PLAN for the STATUS flip). M2
  correctly did **not** modify `compact.py` source (the
  `MicroCompactor` guard already existed at `compact.py:303`), adding
  only the missing negative test — a sub-scope reduction, not creep.
- **Divergence discipline 5/5/5**: M2 recorded 3 deviations (resolution
  placement, compact.py untouched, constant reuse) and M3 recorded 2
  (`_scan_value` bracket superset, `--help` whitespace-normalized match),
  each with a "why" and an "impact on next milestone" line. The
  resolution-placement deviation is captured in ADR-0001 (below).
- **Failure-path coverage 5/5/5**: M1 added closed-stream guard tests +
  a `RuntimeError`-still-propagates negative + 4 secret-leak shapes; M2
  added `MicroCompactor(0)` → `ValueError` + explicit-override matrix
  rows; M3 added the all-9-dirs-taken → `SystemExit` path + parser
  backward-compat regression. None of the milestones shipped happy-path-only.

## Auto-applied edits

- Tier A | (none) | no Tier A trigger fired | trigger: diff added no new `src/*.py` file, no new `[project.scripts]` entry, no new dependency, and no new CLI flag (M2 changed *defaults* of pre-existing flags, not the flag set).
- Tier B | `docs/DECISIONS/README.md` | created ADR index (table: Number/Date/Title/Status/Initiative) because `docs/DECISIONS/` did not exist | trigger: ADR-creation trigger fired (see next row); index is its prerequisite.
- Tier B | `docs/DECISIONS/0001-centralize-threshold-precedence-resolution.md` | ADR for M2's decision to centralize threshold precedence in `cli._resolve_threshold` / `_build_repl_loop` (shared by both REPLs) instead of inline in `_run_repl` | trigger: HANDOFF Section 2 holds ≥2 divergences and ≥1 is architectural (a new shared abstraction deliberately placed to make CLI drift impossible by construction).

The Tier B subsystem-doc trigger did **not** fire: the initiative added
no new `src/` subdirectory and no new module (the diff modified only the
3 existing files `trace.py`, `cli.py`, `openai_cli.py`).

## Proposed edits (need human review)

1. `initiatives/_archive/2026-05-obs-thr-harden/PROGRESS.md` (M1 + M2 `commit:` lines) and `HANDOFF.md` Section 2 (`### M1`, `### M2` commit lines) — correct the unreachable pre-amend SHAs to the reachable ones — why: `71d3c80` (M1) and `30945de` (M2) are not ancestors of HEAD (verified via `git merge-base --is-ancestor`) and will be garbage-collected, breaking `git show <sha>` traceability. The real commits are `6284ea8` and `4056370`. Left as a proposal (not auto-applied) because it edits existing prose in archived bookkeeping files.
   Suggested diff (PROGRESS.md, illustrative):
   ```diff
   - - commit: `71d3c80` `[obs-thr-hd/M1] harden StderrTracer + expand leak/roundtrip coverage`
   + - commit: `6284ea8` `[obs-thr-hd/M1] harden StderrTracer + expand leak/roundtrip coverage`
   ...
   - - commit: `30945de` [obs-thr-hd/M2] fix preset bug + 8-field precedence matrix + MicroCompactor guard test
   + - commit: `4056370` [obs-thr-hd/M2] fix preset bug + 8-field precedence matrix + MicroCompactor guard test
   ```

2. `automation/templates/milestone_prompt.md` §5 (or the exit-ritual SHA step) — standardize the commit-SHA recording on M3's two-commit pattern (or drop the SHA from PROGRESS/HANDOFF and cite "HEAD at commit time") — why: `git commit --amend` to embed a commit's own SHA is self-referential and leaves the recorded SHA unreachable; M3's second-commit approach (`4582997`) is the correct, reproducible fix. Codifying it prevents Proposed edit #1 from recurring every initiative.
   Suggested diff (illustrative):
   ```diff
   - The shell loop's first exit-gate check is `git log -1 ...`.
   + Do NOT `--amend` to embed the commit SHA — that leaves the recorded
   + SHA unreachable. Either omit the SHA (cite "HEAD at commit time") or
   + add a second `[<prefix>/M{N}]` commit that fills it in (see M3).
   ```

3. `src/simple_coding_agent/openai_cli.py` — delete the now-dead `_DEFAULT_MAX_STEPS` constant — why: M2's HANDOFF self-flagged it as dead (max-steps resolution flows through `cli._resolve_threshold` via `_build_repl_loop`). Left for human review since it is a source deletion outside any milestone's scope; trivial follow-up cleanup.

4. `python-replica/CLAUDE.md` `trace.py` per-file summary — add one clause noting the closed-stream `(OSError, ValueError)` guard and `_render_value` repr-quoting that M1 added — why: the summary still describes only the original behavior; the hardening is now load-bearing (it backs `test_null_tracer_zero_overhead` and the demo parser contract). Tier C because it paraphrases an existing summary paragraph rather than appending. (LOW / optional — the summary is not inaccurate, only incomplete.)

## Phase 2C: Wrap-up actions taken

- `git mv initiatives/current initiatives/_archive/2026-05-obs-thr-harden`
- `mkdir initiatives/current && touch initiatives/current/.gitkeep`
- Rewrote `NOW.md` (no active initiative; last completed = obs-thr-harden with final numbers).
- Updated `initiatives/README.md` (moved row Active → Archived; final commit, period, milestone count).
- Wrote `initiatives/_archive/2026-05-obs-thr-harden/logs/review.log`.
- Committed everything as `[obs-thr-hd/wrap] post-execution review + archive`.

(Exact commands are recorded in `logs/review.log`.)
