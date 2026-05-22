# REVIEW — observable-thresholds

## Summary

- **Initiative period**: 2026-05-22 → 2026-05-23
- **Milestones**: 3 (M1, M2, M3) — all complete
- **pytest**: 520 → 557 (Δ +37)
- **mypy**: clean (21 source files); **ruff**: clean
- **Total commits in this initiative**: 8 (3 milestone commits — `063d5d9`, `43e6ee8`, `026db2e` — plus 4 harness/automation commits and 1 bootstrap commit, all in `2d414d91..HEAD`)
- **Lessons learned**:
  - **What worked**: The §2.5 "Out of scope" block in each prompt is doing real work — every milestone stayed inside its lane. The `_AGGRESSIVE_THRESHOLDS` module-level dict invariant declared in M2's HANDOFF §4 ("M3's `visibility_full_demo.py` imports this dict by name; key set is frozen") was honored verbatim by M3. The append-only contract on HANDOFF §2 and PROGRESS was respected across all three milestones.
  - **What worked**: Manual exit-ritual collation as an explicit RUNBOOK recovery path. Two of three milestones (M1, M2) hit autonomous-agent termination conditions (thrash-loop protection and API quota exhaustion); both shipped clean commits via the documented manual collation route. The HANDOFF "known limitations" field made the recovery traceable instead of hidden.
  - **What to do differently next time**: M1's milestone-sizing was too heavy for a single Claude Code session — 11 src files + 5 test files + a cross-cutting `Tracer` Protocol triggered the thrash-loop exit at turn 243. RUNBOOK's "Milestone sizing assessment" section (added during this initiative, see commit `5ee3e88`) now flags this pattern at planning time. Future initiatives should propose a 3-way split (introduce abstraction / wire into components / expose via CLI) when an M{N} combines all three.
  - **What to do differently next time**: PROGRESS.md and HANDOFF.md committed SHAs (`a052056`, `14299af`) do not match actual git log SHAs (`063d5d9`, `43e6ee8`). The agents recorded SHAs from a working-tree state that was later amended by interleaved automation fixes. Future milestone exit rituals should record the SHA via `git rev-parse HEAD` *after* the commit lands, not from earlier state.

## Phase 2B-3: Prompt quality scorecards

| Dimension | M1 | M2 | M3 | Notes |
|---|---|---|---|---|
| Clarity | 5 | 5 | 5 | Each prompt opens with role + termination contract; sections are numbered and unambiguous. |
| Completeness | 5 | 5 | 5 | All of §1–§5 substantively filled in every prompt. |
| Scope alignment | 5 | 5 | 5 | §2 scope + exit gate match PLAN/config milestone tables verbatim (exit_gate text is copy-paste identical). |
| Constraint specificity | 5 | 5 | 5 | TDD, file-size limits, no `git add -A`, no new deps, immutability all called out concretely with reasons. |
| Exit-ritual correctness | 5 | 5 | 5 | §5 mirrors `automation/templates/milestone_prompt.md` §5 with milestone-specific block-shape examples. M3 correctly adds the "last milestone only" PLAN STATUS step. |
| Out-of-scope enumeration | 5 | 5 | 5 | Each §2.5 lists 8–10 concrete "do not" items naming sibling milestones, harness files, public-API freezes, dep additions, and append-only invariants. Not a generic disclaimer. |
| Mandatory reading completeness | 5 | 5 | 5 | M1 has 6 reads (no git log / prior log needed, N=1). M2 has 7 (adds git log). M3 has 8 (adds M2.log + git log). Matches the conditional schedule. |
| Exit gate objectivity | 5 | 5 | 5 | Every exit gate quotes concrete commands and grep counts (`grep -c '^\[trace\] \[budget\]'`, `pytest --tb=no -q total >= N`, `exit code 2`/`3`). No subjective language. |

## Phase 2B-4: Execution quality scorecards

| Dimension | M1 | M2 | M3 | Notes |
|---|---|---|---|---|
| Commit hygiene | 5 | 5 | 5 | All subjects `[obs-thr/M{N}] <one-liner>`; bodies explain mechanism + why. |
| Test growth | 5 | 4 | 4 | M1: 520→542 (+22, target ≥540, +2 over). M2: 542→551 (+9, target ≥545, +6 over). M3: 551→557 (+6, target ≥550, +7 over). All targets met. |
| Gate honor | 5 | 5 | 5 | mypy + ruff clean at every milestone. |
| Divergence discipline | 4 | 3 | 5 | M1: one divergence (`super().__init__()` chain in subclasses) clearly documented with file+line refs and impact. M2: **no `design decisions (deviations from PLAN)` subsection at all**, yet M2 added `MicroCompactor.threshold_minutes` constructor param (implicit-but-required to wire `microcompact_minutes` from the preset). The choice of constructor-param-vs-method-param was not documented. M3: two divergences (`--output-root` flag added beyond PLAN; exit-code-3 semantics adjudication between M2 HANDOFF advisory and M3 prompt) both well-documented with rationale + impact. |
| Log cleanliness | 5 | 5 | 5 | M1/M2 logs are 1B/61B — known artifact of mid-session termination (thrash-loop protection / API quota), not penalized per review-prompt anomaly note. M3 log is 1191B and content-rich (lists all 6 exit-gate checks + result). |
| Implementation matches PLAN | 5 | 5 | 5 | M1: all 9 channels (`compact`, `reactive`, `microcompact`, `snip`, `externalize`, `memory_select`, `claude_md`, `auto_learn`, `budget`) emit at distinct fire sites (verified via `grep emit\(` across `src/`); `NullTracer.emit` body is literally `pass`. M2: `_AGGRESSIVE_THRESHOLDS` is module-level in `cli.py`, all 8 keys present and frozen; `SnipTool(keep_recent=3)` default preserves existing behavior. M3: four artifacts written, exit codes 2 + 3 distinct, `.gitignore` updated in same commit. |
| Scope discipline | 5 | 4 | 5 | M1: stayed inside PLAN expected-files list (11 src + tests + bookkeeping). M2: PLAN expected files did NOT list `compact.py`, but M2 modified it to add `MicroCompactor.threshold_minutes` constructor param. Required to honor the preset wiring but should have been pre-listed. M3: stayed in scope (visibility_full_demo + tests + .gitignore + README + PLAN STATUS). |
| HANDOFF accuracy | 4 | 4 | 5 | M1's HANDOFF claims commit `a052056` — actual SHA is `063d5d9`. M2's HANDOFF claims `14299af` — actual is `43e6ee8`. Both stale because subsequent harness commits (`5ee3e88`, `a064de5`, `9cb9653`) interleaved between milestones and SHAs were not re-captured after rebase. Otherwise file lists, test counts (542 / 551 / 557), and behavior claims match the actual diff. M3 commit was still pending at HANDOFF-write time (`TBD`), now resolved to `026db2e`. |
| Failure-path coverage | 4 | 4 | 4 | M1: `tests/test_trace.py` includes one secret-leak negative test (`test_stderr_tracer_no_raw_user_input_through_repl`) + channel-coverage tests. M2: precedence-rule test + banner-emission test cover the override branch but no "what if user passes invalid threshold" path. M3: tests cover (a) exit-2 missing-flag, (b) exit-3 missing-key — both failure paths. Across all three, the negative-path ratio is reasonable (~25–30% of new tests) but no boundary or invalid-input cases beyond the gated ones. |

## Auto-applied edits

- Tier A | `CLAUDE.md` | Appended `### trace.py` per-file summary section for the new module exporting `Tracer`, `NullTracer`, `StderrTracer` | trigger: `src/` has a new `.py` file (`trace.py`) with public symbols not yet in CLAUDE.md per-file summary table

Tier B triggers did not fire:
- Subsystem doc: `trace.py` is 86 LOC, fails the >150 LOC requirement.
- ADR: no divergence used the architectural keyword list (`renamed module`, `new abstraction`, `dropped feature`, `protocol change`, `inverted dependency`); the three divergences (M1 `super().__init__()`, M3 `--output-root`, M3 exit-code-3 semantics) are coordination/scope adjustments, not architectural pivots. None touched >2 source files.

## Proposed edits (need human review)

1. **`initiatives/_archive/2026-05-observable-thresholds/PROGRESS.md`:24, :33** — SHA recorded as `a052056` / `14299af` does not match git log (`063d5d9` / `43e6ee8`). The discrepancy is cosmetic for the archive but breaks any reader who runs `git show a052056`. Tier C because rewriting historical PROGRESS in the archive is a judgment call (the archive is supposed to be frozen; correcting it post-hoc deviates from the append-only invariant).
   Suggested diff (PROGRESS lines 24, 33):
   ```diff
   -- **commit**: `a052056` `[obs-thr/M1] wire Tracer Protocol + --verbose flag across context/memory pipeline`
   +- **commit**: `063d5d9` `[obs-thr/M1] wire Tracer Protocol + --verbose flag across context/memory pipeline`
   ...
   -- **commit**: `14299af` `[obs-thr/M2] add --aggressive-thresholds preset + SnipTool/MicroCompactor constructor params`
   +- **commit**: `43e6ee8` `[obs-thr/M2] add --aggressive-thresholds preset + SnipTool/MicroCompactor constructor params`
   ```

2. **`README.md` (Console scripts section, after line 75)** — `--verbose` and `--aggressive-thresholds` are new visible CLI surfaces on both entry points (`simple-agent`, `simple-agent-openai`) but README has no flag documentation at all. A user finding these flags via `--help` is fine, but the README's "Status and ongoing work" claim is misleading without at least a one-line "Observability" callout. Tier C because the README structure does not have an obvious flag-list to append to; inserting one would reorganize the Console scripts section.
   Suggested diff:
   ```diff
    | `simple-agent-openai` | `simple_coding_agent.openai_cli` | **Calls the real OpenAI-compatible Chat Completions API.** Loads `.env` by default; pass `--no-dotenv` to skip. |
   +
   +Both entry points support `--verbose` (stream `[trace] [<channel>] …` events to stderr) and `--aggressive-thresholds` (lower compact/snip/microcompact thresholds for demo-friendly behavior; prints a banner summarizing the preset).
   ```

3. **`CLAUDE.md` "Implementation Roadmap" section (after the existing P9-M5 bullet)** — a P9-M6 / new-roadmap-entry summarizing the observable-thresholds initiative would parallel the existing P-roadmap style and let future readers trace `Tracer` / `_AGGRESSIVE_THRESHOLDS` / `visibility_full_demo.py` back to a shipped initiative. Tier C because the Implementation Roadmap section is explicitly carved out from Tier A (per RUNBOOK Doc-update tiers: "Never touch the 'Implementation Roadmap (Completed P1–P8)' section of CLAUDE.md"), and the wording is non-mechanical.

## Phase 2C: Wrap-up actions taken

(See the `[obs-thr/wrap]` commit body for the concrete commands executed in steps 7–10.)
