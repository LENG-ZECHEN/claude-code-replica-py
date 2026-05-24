<!--
PROMPT for the script-spawned review + wrap-up session.

automation/scripts/run_all_milestones.sh invokes one final
`claude --remote-control` after all milestones pass their exit gate.
The script substitutes ctx-mgmt-demo, ctx-demo,
2026-05-ctx-mgmt-demo, and 9ba662bf65e45d08949d4524203773a63bf36902 (4 tokens) before piping
this file as stdin.

This is the MULTI-AGENT review-and-repair version: the main review
session acts as orchestrator. It runs code-reviewer +
doc-curator-candidate-finder in parallel as READ-ONLY subagents,
reconciles their outputs, repairs selected Tier A/B/C findings itself,
then runs demo-narrator after repair/re-review so the Chinese owner
brief can include the findings and fixes that matter.

Outputs:
- REVIEW.md — English archive review for cross-initiative comparison.
- OWNER_BRIEF.zh-CN.md — Chinese owner-facing brief for understanding,
  demo, before/after, and interview/resume storytelling.

Phase 2B may create focused review-fix/review-doc commits before wrap.
Phase 2C then archives the initiative, rewrites NOW.md, updates index
files, commits the final wrap result, then stays alive on --remote-control
so the human can attach and ask follow-up questions.

Comment blocks (HTML comments) are guidance and should NOT appear in
REVIEW.md or OWNER_BRIEF.zh-CN.md.
-->

# Phase 2B + 2C — Multi-agent review + wrap-up for `ctx-mgmt-demo`

You are the **MAIN REVIEW AGENT** for the `ctx-mgmt-demo`
initiative. Every milestone has already produced its commit. Your job
is to perform a staged multi-agent review, archive the initiative, and
remain available for human follow-up via `--remote-control`.

Your work has 5 acts:

1. **Phase 2B preflight**: verify every milestone commit exists and the
   initial final quality gates are green enough to begin review. If a
   gate is red but the failure is clearly repairable inside the review
   session, you may enter review-and-repair mode instead of stopping.
   Missing milestone commits are hard blockers.
2. **Phase 2B multi-agent review**:

   * Stage A: spawn 2 READ-ONLY subagents in parallel:
     `code-reviewer` and `doc-curator-candidate-finder`.
   * Stage B: reconcile their outputs yourself. Do not blindly paste
     contradictory or duplicated findings.
   * Stage C: perform review-time repair. The MAIN REVIEW AGENT may
     autonomously repair selected Tier A/B/C findings when the repair is
     safe, scoped, testable, and valuable. Stage A subagents remain
     read-only; only the MAIN REVIEW AGENT may edit, test, stage, or
     commit.
   * Stage D: apply approved documentation edits, then re-review the
     repaired state.
   * Stage E: spawn `demo-narrator` with the final reconciled findings
     and review-time repair outcomes so the Chinese owner brief reflects
     what actually shipped after review.
3. **Phase 2C wrap-up**: create `REVIEW.md` and
   `OWNER_BRIEF.zh-CN.md`, archive `initiatives/current/`, rewrite
   `NOW.md`, update `initiatives/README.md`, write `review.log`, and
   commit the final archive result as `[ctx-demo/wrap]`.
4. **Final exit-gate verification**: ensure tests, archive/current state,
   and git state are coherent after any review-time repair commits. The
   final HEAD should be the `[ctx-demo/wrap]` commit.
5. **Stay alive on `--remote-control`**. After the wrap-gate verifies,
   print the exact attach message in Step 11. Do NOT `/exit`. The
   session terminates only when the user `/exit`s manually.

There is no user available during Phase 2B / 2C. Stop only on a clear
quality failure that cannot be repaired within this review session:
missing milestone commit, persistent pytest red, persistent mypy red,
persistent ruff red, unsafe repair scope, or repeated validation failure.
After Phase 2C, the user attaches via browser extension or Claude
desktop app to ask follow-up questions in any language.

## Mandatory reading — main agent reads this FIRST

Read these before spawning any subagents:

1. `python-replica/automation/RUNBOOK.md` — your role is documented in
   Phase 2B + 2C. Read the section "Doc-update tiers (used by Step 6)"
   carefully because YOU, not the doc-curator subagent, will apply Tier
   A/B edits after reconciliation.
2. `python-replica/initiatives/current/PLAN.md` — the original brief.
3. `python-replica/initiatives/current/config.yaml` — milestone table.
4. Every `python-replica/initiatives/current/prompts/M{N}.md` —
   per-milestone prompts.
5. Every `python-replica/initiatives/current/logs/M{N}.log` — raw run
   logs.
6. `python-replica/initiatives/current/HANDOFF.md` — terminal state.
7. `python-replica/initiatives/current/PROGRESS.md` — per-milestone log.

You do NOT need to read every source file hunk before spawning Stage A
subagents. The `code-reviewer` subagent does the full source/test diff
review. You need enough understanding to coordinate, reconcile, write a
sensible summary, and safely apply doc edits.

---

# Phase 2B — Review

## Step 1: Verify completion

For every M{N} in `config.yaml`:

```bash
git -C python-replica log 9ba662bf65e45d08949d4524203773a63bf36902..HEAD --oneline | grep -F "[ctx-demo/M{N}]"
```

This must return at least one match. The `9ba662bf65e45d08949d4524203773a63bf36902..HEAD`
range restricts the search to THIS initiative's commits, preventing
false positives from prior archived initiatives that reused the same
`commit_prefix`. `9ba662bf65e45d08949d4524203773a63bf36902` was substituted by the shell
script from `initiatives/current/config.yaml` during Phase 1.

If any milestone is missing its commit:

1. STOP.
2. Write `initiatives/current/REVIEW.md` with only a `# BLOCKED` section
   explaining which milestone is missing and why.
3. Do NOT spawn subagents.
4. Do NOT create `OWNER_BRIEF.zh-CN.md`.
5. Do NOT run Phase 2C archive / wrap-up steps.

## Step 2: Snapshot final numbers

```bash
cd python-replica
pytest --tb=no -q       # record total passing
mypy src/               # record status
ruff check .            # record status
```

If pytest is red OR mypy is red OR ruff is red:

1. First decide whether the failure is clearly repairable inside this
   review session.
2. If the failure is not safely repairable, STOP and write
   `initiatives/current/REVIEW.md` with only a `# BLOCKED` section
   quoting the failing output. Do NOT spawn subagents, do NOT create
   `OWNER_BRIEF.zh-CN.md`, and do NOT run Phase 2C archive / wrap-up
   steps.
3. If the failure is safely repairable, record the failing output as an
   initial gate failure, continue into Stage A review, and repair it in
   Step 3C before any final REVIEW.md / OWNER_BRIEF / archive work.

Record:

* final pytest count
* baseline pytest count, if available from PROGRESS.md / PLAN.md
* pytest delta
* mypy status
* ruff status
* final commit SHA before wrap
* number of commits in `9ba662bf65e45d08949d4524203773a63bf36902..HEAD`
* start/end dates from first and last initiative commits

---

## Step 3A: Spawn 2 READ-ONLY subagents in parallel

In a **SINGLE message**, issue **2 `Agent` tool calls**:

1. `code-reviewer`
2. `doc-curator-candidate-finder`

They must run in parallel. Wait for both to return before proceeding.

For each subagent:

* `subagent_type` = `"general-purpose"`
* `description` = the short label given below
* `prompt` = the literal markdown text between
  `----- BEGIN PROMPT[<role>] -----` and
  `----- END PROMPT[<role>] -----` for that role, with the 4
  `{{...}}` tokens already substituted by the shell script.

Important: **both Stage A subagents are read-only**. They must not edit,
write, stage, commit, delete, move, or archive any file. The MAIN REVIEW
AGENT is the only writer.

---

## Subagent 1: `code-reviewer`

`description`: `"code-review-for-ctx-mgmt-demo"`

----- BEGIN PROMPT[code-reviewer] -----

You are the **code-reviewer subagent** for the `ctx-mgmt-demo`
initiative. You evaluate prompt quality, execution quality, and concrete
code correctness risks for this initiative's diff.

You are READ-ONLY. Do not modify any file.

## §Role

Audit every milestone on two scorecard axes:

1. **Prompt quality** — how well-written was each `prompts/M{N}.md`?
   Was it clear, complete, scope-aligned, constraint-specific, and
   exit-ritual-correct?
2. **Execution quality** — how well did the milestone agent execute
   against the prompt and PLAN? Did the commit match the plan, were
   tests meaningful, were failures/edge paths covered, and did it stay
   in scope?

Additionally, surface **detail-level findings**: concrete bugs,
correctness risks, missing edge cases, fragile patterns, misleading
claims, or implementation-depth gaps introduced by the initiative diff.

## §Inputs

Read in this order before scoring:

1. `python-replica/initiatives/current/PLAN.md`
2. `python-replica/initiatives/current/config.yaml`
3. Every `python-replica/initiatives/current/prompts/M{N}.md`
4. Every `python-replica/initiatives/current/logs/M{N}.log`
5. `python-replica/initiatives/current/HANDOFF.md` Section 2
6. `python-replica/initiatives/current/PROGRESS.md`
7. `git -C python-replica log 9ba662bf65e45d08949d4524203773a63bf36902..HEAD --oneline`
8. `git -C python-replica diff 9ba662bf65e45d08949d4524203773a63bf36902..HEAD -- src/ tests/`
9. Each milestone's individual commit:

   * `git -C python-replica show <commit> --stat`
   * selected hunks from `git -C python-replica show <commit>`

## §Output schema

Return ONE markdown block in EXACTLY this shape. The main agent will
reconcile and splice it into `REVIEW.md`.

```markdown
## Phase 2B-3: Prompt quality scorecards

For each `prompts/M{N}.md`, score on 8 dimensions (1-5 each):

| Milestone | Clarity | Completeness | Scope alignment | Constraint specificity | Exit-ritual correctness | Out-of-scope enumeration | Mandatory reading completeness | Exit gate objectivity | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 40/40 |
| M2 | ... | ... | ... | ... | ... | ... | ... | ... | ... |

For each row whose total < 36/40, add one explanatory bullet beneath
the table explaining why a dimension was docked.

## Phase 2B-4: Execution quality scorecards

For each milestone, score on 9 dimensions (1-5 each):

| Milestone | Commit hygiene | Test growth | Gate honor | Divergence discipline | Log cleanliness | Implementation matches PLAN | Scope discipline | HANDOFF accuracy | Failure-path coverage | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 45/45 |
| M2 | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

Add explanatory bullets for any row whose total < 40.5/45.

## Detail-level findings

List concrete bugs / correctness risks / fragile patterns surfaced by
reading the diff. Bullet shape:

- **<short title>** — `<file>:<line>` — <severity: HIGH | MEDIUM | LOW>
  - **What**: <1-2 sentences describing the issue>
  - **Why it matters**: <1 sentence>
  - **Fix sketch**: <1-2 sentences>

If no detail findings: write
"(none — no detail-level issues found)".
```

## §Scoring dimensions

Prompt quality dimensions:

| Dimension                      | What to look for                                                              |
| ------------------------------ | ----------------------------------------------------------------------------- |
| Clarity                        | Can a fresh session execute this without ambiguity?                           |
| Completeness                   | Are required sections present and substantively filled?                       |
| Scope alignment                | Do scope + exit gate match PLAN's milestone entry?                            |
| Constraint specificity         | Are TDD / file-limit / no-`-A` / no-unrelated-refactor requirements explicit? |
| Exit-ritual correctness        | Does the prompt enforce the expected milestone exit ritual?                   |
| Out-of-scope enumeration       | Does it list concrete do-not items, not just generic disclaimers?             |
| Mandatory reading completeness | Does it list all required mandatory reads for the milestone?                  |
| Exit gate objectivity          | Is the exit gate objectively verifiable by command output?                    |

Execution quality dimensions:

| Dimension                   | What to look for                                                                |
| --------------------------- | ------------------------------------------------------------------------------- |
| Commit hygiene              | Subject matches `[ctx-demo/M{N}]`; body explains why.                  |
| Test growth                 | Did pytest grow as expected? Were new tests meaningful?                         |
| Gate honor                  | mypy + ruff stayed clean.                                                       |
| Divergence discipline       | Deviations from PLAN are explained in HANDOFF Section 2.                        |
| Log cleanliness             | No unexplained errors / warnings / retries in milestone logs.                   |
| Implementation matches PLAN | Diff actually delivers the planned behavior, not just passing tests.            |
| Scope discipline            | Touched files match expected files + tests + required bookkeeping.              |
| HANDOFF accuracy            | Claimed behavior/files/tests match actual diff and PROGRESS.md.                 |
| Failure-path coverage       | Tests include invalid input, edge cases, or failure paths, not only happy path. |

## §Constraints

* Do NOT modify any file.
* Do NOT propose documentation edits except when a code finding depends
  on a misleading document claim; even then, phrase it as a risk, not as
  a doc-curator proposal.
* Do NOT write Chinese summaries or demo walkthroughs.
* Do NOT invent new scorecard dimensions.
* Cite every detail finding with `<file>:<line>` or commit SHA.
* A milestone whose new tests are all happy-path should be flagged under
  Failure-path coverage and, if meaningful, as a LOW or MEDIUM detail
  finding.
* Be strict about implementation depth. Passing tests are evidence, not
  proof.

----- END PROMPT[code-reviewer] -----

---

## Subagent 2: `doc-curator-candidate-finder`

`description`: `"doc-curator-candidates-for-ctx-mgmt-demo"`

----- BEGIN PROMPT[doc-curator-candidate-finder] -----

You are the **doc-curator-candidate-finder subagent** for the
`ctx-mgmt-demo` initiative. You identify which project docs may
need syncing because of this initiative's production-code diff.

You are READ-ONLY. Do not modify any file. Do not apply Tier A/B edits.
The MAIN REVIEW AGENT will reconcile your candidate list and apply any
approved Tier A/B edits itself.

## §Role

Classify doc-change candidates into three tiers per the RUNBOOK section
"Doc-update tiers (used by Step 6)":

* Tier A candidates: safe append-only mechanical edits.
* Tier B candidates: new file creations such as subsystem docs or ADRs.
* Tier C proposals: changes requiring rewrite, deletion, reorganization,
  or subjective human judgment.

Your output is advisory. The main agent is responsible for final
selection, edits, staging, and commit.

## §Inputs

1. `python-replica/automation/RUNBOOK.md` — read section
   "Doc-update tiers (used by Step 6)" verbatim.
2. `git -C python-replica diff 9ba662bf65e45d08949d4524203773a63bf36902..HEAD --stat -- src/ pyproject.toml`
3. `git -C python-replica diff 9ba662bf65e45d08949d4524203773a63bf36902..HEAD --name-only -- src/ pyproject.toml`
4. `git -C python-replica diff 9ba662bf65e45d08949d4524203773a63bf36902..HEAD -- src/ pyproject.toml`
5. `python-replica/initiatives/current/HANDOFF.md` — Section 2 design
   decisions / deviations from PLAN.
6. `python-replica/initiatives/current/PLAN.md`
7. `python-replica/CLAUDE.md`
8. `python-replica/README.md`
9. `python-replica/docs/` if it exists.
10. `python-replica/automation/templates/subsystem_doc.md`
11. `python-replica/automation/templates/adr.md`

## §Output schema

Return ONE markdown block in EXACTLY this shape. The main agent will
reconcile it, then apply approved Tier A/B edits itself.

````markdown
## Doc-update candidates

### Tier A candidates — safe append-only

If any Tier A candidate exists, list one bullet per candidate:

- Tier A candidate | `<target file>` | <one-line candidate edit> | trigger: <exact RUNBOOK Tier A rule> | confidence: <HIGH | MEDIUM | LOW>
  - Suggested append location: <section / line anchor>
  - Suggested appended text:
    ```markdown
    <exact append-only text>
    ```

If no Tier A candidate exists, write:

- Tier A candidate | (none) | no Tier A trigger matched | reason: <one-line reason>

### Tier B candidates — new files

If any Tier B candidate exists, list one bullet per candidate:

- Tier B candidate | `<new file path>` | <one-line file purpose> | trigger: <exact RUNBOOK Tier B rule> | confidence: <HIGH | MEDIUM | LOW>
  - Source evidence: <HANDOFF / PLAN / diff reference>
  - Template to use: `<template path>`
  - Placeholder values:
    - `{{placeholder}}`: <value>
  - If creating ADR: proposed ADR title = `<title>`; proposed slug = `<slug>`

If no Tier B candidate exists, write:

- Tier B candidate | (none) | no Tier B trigger matched | reason: <one-line reason>

### Tier C proposals — human review only

For every Tier C candidate:

1. `<file>:<line-or-section>` — <what to change> — why: <reason>
   Trigger: <exact RUNBOOK Tier C rule>
   Suggested diff:
   ```diff
   - <old line>
   + <new line>
````

If no Tier C candidates exist, write:

"(none — no proposed edits)".

````

## §Constraints

- Do NOT modify any file.
- Do NOT score code quality.
- Do NOT write Chinese summaries or demo walkthroughs.
- Every candidate must cite a specific RUNBOOK trigger row.
- Tier A must be safe and append-only. If unsure, mark confidence LOW or
  downgrade to Tier C.
- Tier B should be moderately aggressive, but still only as a candidate.
  The main agent decides whether to actually create files.
- Never propose editing the first 10 lines of `README.md`.
- Never propose editing the "Implementation Roadmap" section of
  `CLAUDE.md` unless RUNBOOK explicitly permits it. Prefer Tier C if
  uncertain.
- If a Tier B target path already exists, say so and recommend either a
  Recent changes append candidate or a Tier C proposal.

----- END PROMPT[doc-curator-candidate-finder] -----

---

## Step 3B: Reconcile Stage A outputs

After `code-reviewer` and `doc-curator-candidate-finder` both return,
perform reconciliation BEFORE writing files or launching demo-narrator.

Create an internal reconciliation note with these decisions:

1. **Final code findings**
   - Deduplicate overlapping findings.
   - Preserve all HIGH findings unless clearly unsupported.
   - If severity seems inflated or understated, adjust severity and
     explain why in `REVIEW.md`.
   - If evidence is weak, mark the finding as "uncertain" rather than
     stating it as fact.

2. **Final prompt/execution scorecards**
   - Use code-reviewer's scorecards as the source of truth unless you
     find an obvious contradiction with mandatory files.
   - Do not silently edit scorecard numbers. If you change them, add a
     short note in `REVIEW.md` explaining the correction.

3. **Final doc-update decisions**
   - For each Tier A candidate, decide APPLY / DOWNGRADE TO TIER C / SKIP.
   - For each Tier B candidate, decide CREATE / DOWNGRADE TO TIER C / SKIP.
   - For each Tier C candidate, decide INCLUDE / SKIP.
   - Reasons must be recorded in `REVIEW.md` under Auto-applied edits or
     Proposed edits.

4. **Owner-facing findings**
   - Pick the findings that the human owner should see in Chinese.
   - Include all HIGH code findings.
   - Include MEDIUM findings if they affect demo, correctness,
     maintainability, or interview/storytelling.
   - Include Tier C doc proposals only if they materially affect the
     user's understanding of what shipped.
   - Exclude bookkeeping noise.

Do not create a separate reconciliation file unless it is useful. The
reconciled decisions must be reflected in `REVIEW.md` and passed to
`demo-narrator`.

---


---

## Step 3C: Review-time repair loop

After reconciling Stage A outputs, the MAIN REVIEW AGENT enters
review-and-repair mode.

You are not merely a reviewer. You are a review-and-repair agent. Your
job is to make the initiative genuinely shippable, not merely to report
defects.

### Finding tiers

Classify reconciled findings into:

- **Tier A**: correctness bugs, data loss risks, security risks, broken
  CLI/API behavior, broken tests, corrupted archive state, or anything
  that makes the initiative unsafe to ship.
- **Tier B**: wired-but-inert behavior, misleading trace/metrics,
  incomplete integration, missing end-to-end coverage, stale claims that
  materially misrepresent behavior, or important maintainability issues.
- **Tier C**: documentation polish, small cleanup, optional refactors,
  minor consistency issues, or future improvement opportunities.

### Repair policy

- Tier A findings must be fixed if technically feasible within this
  review session. If not fixable safely, stop and write a BLOCKED review
  explaining the blocker.
- Tier B findings should be fixed when the change is local, testable,
  and unlikely to expand scope.
- Tier C findings may be fixed autonomously if the change is small,
  low-risk, and improves the final deliverable.
- Do not expand Tier C into broad refactors, new features, or subjective
  redesigns.
- Do not hide unresolved findings. Either fix them, downgrade them with
  justification, or record them as follow-ups in REVIEW.md.
- If a finding was discovered and then repaired during this review
  session, record it under "Fixed during review", not as an unresolved
  defect.

### Repair budget

You may perform up to 5 repair rounds.

Each repair round must have a clear target:

- finding being addressed,
- intended files,
- proof/test required,
- expected commit type.

For each repair round:

1. Select the highest-value unresolved finding that is safe to fix.
2. Make the smallest sufficient change.
3. Add or update tests first when practical.
4. Run targeted validation for the changed area.
5. If targeted validation passes, continue to the next finding or the
   final validation gate.
6. If targeted validation fails, repair once more.
7. If the same validation failure repeats twice, stop that repair path
   and document the blocker.

Do not run an unbounded loop. Do not start unrelated features. Do not
rewrite unrelated subsystems.

### Review-time commit rules

Review-time code/test fixes must be committed before Phase 2C wrap-up as:

`[ctx-demo/review-fix] <short description>`

Review-time documentation-only fixes made before Phase 2C wrap-up must be
committed as:

`[ctx-demo/review-doc] <short description>`

If a commit contains both code and docs required for the same finding,
use `review-fix`.

Every review-time commit must be focused and must mention the finding or
issue it addresses.

Do not squash review-time repair commits into the final wrap commit. The
final `[ctx-demo/wrap]` commit should archive and summarize the
repaired final state.

Do not leave unstaged or uncommitted repair changes before entering Phase
2C. Before Step 4, `git status --short` should be clean except for files
that Step 4 / Step 5 are about to create.

### Validation inside the repair loop

For every repaired finding:

1. Run targeted tests that prove the fix.
2. If tests had to be added, confirm the new test would have failed
   before the repair when practical.
3. Record the targeted command and result for REVIEW.md.
4. After all selected repairs, run the final validation gate:

```bash
python -m pytest tests/ -q
python -m mypy src/simple_coding_agent
python -m ruff check src tests
git status --short
```

If the project has a stricter canonical gate, run that as well.

### Re-review after repair

After repair rounds are complete, re-review the repaired state before
writing REVIEW.md or spawning `demo-narrator`.

Confirm:

- selected Tier A/B/C repairs are complete,
- targeted tests passed,
- full final validation passed or blockers are explicitly documented,
- all review-time repair changes are committed,
- working tree is clean except for pending REVIEW.md / OWNER_BRIEF files,
- any remaining findings are accurately described as follow-ups.

Do not write the final REVIEW.md before this re-review is complete.

## Step 3D: Apply approved documentation edits yourself

Only the MAIN REVIEW AGENT may modify files.

This step happens after the review-time repair loop. It covers
documentation updates that remain after code/test repairs are complete.

The MAIN REVIEW AGENT may apply Tier A/B documentation edits and may also
apply small, low-risk Tier C documentation edits if they are clearly safe
and improve the final deliverable. Broad rewrites, subjective
reorganizations, or schema changes must remain proposals.

Read `automation/RUNBOOK.md` section "Doc-update tiers (used by Step 6)"
again before applying edits.

Run the production diff once at the top of this step:

```bash
git -C python-replica diff 9ba662bf65e45d08949d4524203773a63bf36902..HEAD --stat -- src/ pyproject.toml
git -C python-replica diff 9ba662bf65e45d08949d4524203773a63bf36902..HEAD --name-only -- src/ pyproject.toml
````

Then apply reconciled documentation decisions.

### Tier A — apply automatically only if safe

For each approved Tier A candidate:

1. Locate target file + insertion point.
2. Use Edit to APPEND a row / bullet / section.
3. Do not modify existing content.
4. Do not touch the first 10 lines of README.md.
5. Do not touch the Implementation Roadmap section of CLAUDE.md.
6. Record in `REVIEW.md` later:

```markdown
- Tier A | `<file>` | <one-line summary> | trigger: <RUNBOOK rule> | source: doc-curator candidate / main-agent inspection
```

If unsure whether a candidate is mechanical enough, do NOT apply it.
Downgrade it to Tier C.

### Tier B — create new files if justified

For each approved Tier B candidate:

#### Subsystem doc

1. Copy `automation/templates/subsystem_doc.md` into `docs/<slug>.md`.
2. Fill every `{{placeholder}}` from PLAN.md / HANDOFF.md / diff.
3. If `docs/<slug>.md` already exists, do not overwrite it. Instead,
   append a dated bullet to its `## Recent changes` section if safe;
   otherwise downgrade to Tier C.

#### ADR

1. If `docs/DECISIONS/` does not exist, create it.
2. If `docs/DECISIONS/README.md` does not exist, create it with an index
   table: Number / Date / Title / Status / Initiative.
3. Compute NNNN:

```bash
ls docs/DECISIONS/ | grep -E '^[0-9]{4}' | sort | tail -1 | cut -c1-4
```

Increment by 1 and zero-pad to 4. Start at `0001` if none exists.

4. Slug = kebab-case of the divergence title, <= 6 words.
5. Copy `automation/templates/adr.md` into
   `docs/DECISIONS/<NNNN>-<slug>.md`.
6. Fill every `{{placeholder}}`.
7. Source Context / Decision / Consequences from HANDOFF Section 2 design
   decisions wherever possible.
8. Append a row to `docs/DECISIONS/README.md`.

Record every Tier B creation in `REVIEW.md` later:

```markdown
- Tier B | `<new file path>` | <one-line summary> | trigger: <RUNBOOK rule> | source: doc-curator candidate / main-agent inspection
```

### Tier C — optionally apply if small and safe

Tier C edits are normally proposals, but the MAIN REVIEW AGENT may apply
a Tier C documentation edit when all of the following are true:

1. The edit is small and local.
2. The edit does not rewrite the document structure.
3. The edit does not change table schemas unless the schema change is
   clearly mechanical and low-risk.
4. The edit removes stale or misleading information caused by this
   initiative or review-time repairs.
5. The edit can be reviewed from the final diff.

If applied, record it in REVIEW.md under "Fixed during review" or
"Auto-applied edits" with Tier C classification.

If not applied, put it in REVIEW.md under:

```markdown
## Proposed edits (need human review)
```

Each proposed entry:

````markdown
1. `<file>:<line-or-section>` — <what to change> — why: <reason>
   Trigger: <RUNBOOK rule>
   Suggested diff:
   ```diff
   - old line
   + new line
   ```
````

---

## Step 3E: Spawn demo-narrator AFTER repair and re-review

Now spawn `demo-narrator`. This is intentionally NOT parallel with
Stage A. The narrator must see the repaired final state, the reconciled
review findings, and the review-time repair outcomes so the Chinese
owner brief explains what actually shipped after review.

Use one `Agent` tool call:

- `subagent_type` = `"general-purpose"`
- `description` = `"owner-brief-narrator-for-ctx-mgmt-demo"`
- `prompt` = the literal prompt below PLUS an appended section titled
  `## Additional input from main-agent reconciliation` containing:
  - final code findings retained after re-review
  - findings fixed during review, with commit hashes and test evidence
  - findings deferred, with rationale
  - final Tier A/B/C documentation decisions
  - important doc edits that affect the owner brief
  - final pytest/mypy/ruff numbers after repair
  - final initiative commit range
  - review-time repair commits, if any
  - final pre-wrap commit

---

## Subagent 3: `demo-narrator`

`description`: `"owner-brief-narrator-for-ctx-mgmt-demo"`

----- BEGIN PROMPT[demo-narrator] -----

You are the **demo-narrator subagent** for the `ctx-mgmt-demo`
initiative. Your job is to bridge the cognitive gap between the human
decision-maker, who mainly participated at the initial planning stage,
and the autonomous milestone work that happened afterward.

Your output is in **Chinese (中文)** and becomes the main content of
`OWNER_BRIEF.zh-CN.md`.

You are READ-ONLY. Do not modify any file.

## §Role

Write a Chinese owner-facing walkthrough that answers:

1. **这次交付了什么？** — feature-level, not file-level.
2. **如何演示给别人看？** — concrete commands + expected output.
3. **Before / After 对比？** — baseline behavior vs final behavior.
4. **有哪些项目 owner 必须知道的 finding？** — explain important
   reconciled code/doc findings in Chinese, pruning bookkeeping noise.
5. **如何用于简历 / 面试表达？** — explain the most defensible project
   highlights without exaggeration.

## §Inputs

Read:

1. `python-replica/initiatives/current/PLAN.md`
2. `python-replica/initiatives/current/HANDOFF.md` Section 2
3. `python-replica/initiatives/current/PROGRESS.md`
4. `git -C python-replica log 9ba662bf65e45d08949d4524203773a63bf36902..HEAD --oneline`
5. `git -C python-replica diff 9ba662bf65e45d08949d4524203773a63bf36902..HEAD -- src/ examples/ README.md tests/`
6. `git -C python-replica show <milestone-commit>` for each milestone,
   especially hunks that reveal user-visible behavior, commands, or demo
   output.
7. The appended section from the MAIN REVIEW AGENT:
   `## Additional input from main-agent reconciliation`.

## §Output schema

Return ONE markdown block in EXACTLY this shape. The main agent will
write it into `OWNER_BRIEF.zh-CN.md`.

```markdown
## 这次交付了什么

按功能列出本次 initiative 交付的具体能力。不要只按文件罗列。每项 1-3 行。
每个交付项必须引用具体 file:line 或 commit SHA。

- **<功能 1 名称>** — <一句话说做了什么>。证据：`<file:line>` 或 commit `<sha>`。
- **<功能 2 名称>** — ...

## 如何演示

给出可以复制到终端运行的演示步骤。命令必须来自实际代码 / examples / tests，不要编造。

### 演示场景 A：<场景标题>

```bash
$ <命令 1>
<期望输出片段，<= 3 行，用 ... 截断长输出>

$ <命令 2>
<期望输出片段>
````

### 演示场景 B：<场景标题，如果有多个独立功能>

```bash
$ <命令>
<期望输出片段>
```

如果某个功能是内部 refactor，没有直接 CLI demo，明确写：
"本功能为内部实现改造，无直接 CLI demo；可通过 `<测试 path>` 或
`<代码 path>` 验证。"

## Before / After 对比

| 项        | 之前（baseline `9ba662bf65e45d08949d4524203773a63bf36902`） | 之后（本 initiative 结束） |
| -------- | ---------------------------------- | ------------------- |
| <功能维度 1> | <旧行为>                              | <新行为>               |
| <功能维度 2> | <旧行为>                              | <新行为>               |

至少 2 行。如果功能太内部化，最后一行可以用 pytest count / 测试覆盖增长。

## 用户视角下的关键 finding

只写用户应该知道的实质问题，不重复 scorecard 数字。

* **<finding 标题>** — 严重度 <HIGH/MEDIUM/LOW> — 来源：<code-reviewer finding / doc Tier C proposal / main-agent reconciliation>

  * <中文解释：这是什么问题、为什么影响用户、建议怎么处理>

如果无值得用户特别关注的问题，写：
"(本次未发现需要用户特别关注的问题)"。

## 简历 / 面试可以怎么讲

给出 3-5 条可防守、不过度夸大的表达。每条包括：

* **亮点**：<一句话>

  * **可以怎么说**：<中文表达，必要时附英文关键词>
  * **证据**：`<file:line>` / commit `<sha>` / test command
  * **不要夸大成**：<提醒用户不要怎么说>

## 还需要补什么

列出 1-5 个最值得后续补强的点。按优先级排序。

1. **<补强点>** — <为什么值得补> — <建议下一步>

````

## §Constraints

- 全文用中文；file paths / commit SHAs / CLI flags / code identifiers
  保持英文原样。
- 演示命令必须真实可跑。不要凭想象编造命令。
- 每个交付项必须引用具体 file:line 或 commit SHA。
- 不要写 scorecard。
- 不要提出新的 doc edits。只解释 main-agent reconciliation 传入的 finding。
- 不要修改任何文件。
- 目标是让项目 owner 读完后能快速掌握：做了什么、怎么演示、哪里还不稳、怎么对外讲。

----- END PROMPT[demo-narrator] -----

---

## Step 4: Write `initiatives/current/REVIEW.md`

Use `Write` to create `initiatives/current/REVIEW.md`.

Write REVIEW.md only after the repair loop and re-review are complete.

Structure:

```markdown
# REVIEW — ctx-mgmt-demo

## Summary

- Initiative period: <start> -> <end>
- Milestones: <count>, all complete
- pytest: <before> -> <after> (delta +N)
- mypy: <status>
- ruff: <status>
- Total milestone commits before review: <N>
- Review-time commits: <N>
- Final pre-review commit: `<sha>`
- Final pre-wrap commit after review repairs: `<sha>`
- Wrap commit: `<sha or pending until Phase 2C>`
- Review mode: multi-agent staged review + main-agent repair loop
  (`code-reviewer` + `doc-curator-candidate-finder` in parallel,
  reconciled by main agent, repaired by main agent, then `demo-narrator`)

## Lessons learned

- <3-5 bullets — what worked, what to do differently next time>

## Main-agent reconciliation note

Explain briefly:

- whether code-reviewer and doc-curator outputs conflicted
- which findings were deduplicated or severity-adjusted
- which findings were selected for review-time repair
- which findings were deferred and why
- which Tier A/B/C doc candidates were applied, downgraded, or skipped
- which findings were selected for the owner brief

(paste reconciled code-reviewer's scorecard sections here)

## Findings and repair ledger

### Fixed during review

For each finding fixed during review:

- `<finding title>` — Tier <A/B/C> — severity <HIGH/MEDIUM/LOW>
  - Source: <code-reviewer / doc-curator / main-agent inspection>
  - Fix commit: `<sha> [ctx-demo/review-fix or review-doc] ...`
  - Files changed: `<paths>`
  - Tests added/updated: `<paths or none>`
  - Validation: `<commands and results>`

If none, write "(none)".

### Deferred findings / follow-ups

For each unresolved finding:

- `<finding title>` — Tier <A/B/C> — severity <HIGH/MEDIUM/LOW>
  - Why deferred: <reason>
  - Suggested next step: <concrete next action>

If none, write "(none)".

## Auto-applied edits

<Tier A/B/C doc edits actually applied by the MAIN REVIEW AGENT.
If none: write explicit none rows.>

## Proposed edits (need human review)

<Tier C proposals not applied by the MAIN REVIEW AGENT.
If none: write "(none)".>

## Validation results

Include:

- initial quality gate results,
- targeted tests run for review-time repairs,
- full pytest result after repair,
- mypy result after repair,
- ruff result after repair,
- git status result,
- any failed command and how it was resolved.

## Phase 2C: Wrap-up actions taken

<list what you did in Phase 2C, with commands>

## Owner brief

The decision-maker-facing Chinese owner brief lives in
[`OWNER_BRIEF.zh-CN.md`](./OWNER_BRIEF.zh-CN.md). Read that file for
"what was built / how to demo it / before-after / how to talk about it".
````

Rules:

* Do not blindly paste the raw doc-curator candidate list. Record final
  Tier A/B/C decisions only.
* Do not hide unsupported findings. If a subagent finding was rejected,
  mention it briefly in the reconciliation note.
* Do not describe already-fixed findings as still broken.
* If a finding was discovered and fixed during review, record it under
  "Fixed during review".
* Keep `REVIEW.md` English.
* Keep `OWNER_BRIEF.zh-CN.md` as the Chinese source for human
  understanding.

---

## Step 5: Write `initiatives/current/OWNER_BRIEF.zh-CN.md`

Use `Write` to create `initiatives/current/OWNER_BRIEF.zh-CN.md`:

```markdown
# OWNER BRIEF（中文）— ctx-mgmt-demo

> 本文档给项目 owner 阅读，重点是：这次交付了什么、如何演示、Before/After
> 有什么变化、哪些 finding 需要注意、以及如何把成果用于简历 / 面试表达。
>
> 英文归档审查（含评分卡、Tier A/B/C 决策、wrap-up 记录）见
> [`REVIEW.md`](./REVIEW.md)。

(paste demo-narrator's full reconciled output block here)

## 项目状态一句话

本次 initiative 在 `9ba662bf65e45d08949d4524203773a63bf36902..HEAD` 范围共 <N> 个 commit，
最终 pytest <count> 通过（baseline <before>，+<delta>），mypy + ruff
全绿。完整审核结论见 `REVIEW.md`。
```

Do NOT translate the full scorecards into Chinese. Avoid duplication and
future drift. `OWNER_BRIEF.zh-CN.md` is deliberately scoped to user
understanding and demo readiness.

---

# Phase 2C — Wrap-up

Only proceed if:

1. Step 1 passed.
2. Step 2 was initially green, or any initial repairable failure was
   fixed and the final validation gate is now green.
3. Stage A subagents returned successfully.
4. Main-agent reconciliation completed.
5. Review-time repair loop completed or explicitly found no safe repairs.
6. Re-review of the repaired state completed.
7. Approved documentation edits, if any, were applied by the main agent.
8. `demo-narrator` returned successfully.
9. `REVIEW.md` and `OWNER_BRIEF.zh-CN.md` were written successfully.
10. `git status --short` is clean or only contains files that Phase 2C
    is about to archive/stage explicitly.

## Step 6: Archive

```bash
cd python-replica
git mv initiatives/current initiatives/_archive/2026-05-ctx-mgmt-demo
mkdir initiatives/current
touch initiatives/current/.gitkeep
```

## Step 7: Rewrite `NOW.md`

Use this template. Preserve the prior `## How to start a new initiative`
section verbatim.

```markdown
# NOW — current initiative status

## Active initiative

**None.**

`initiatives/current/` is empty (`.gitkeep` only).

## Last completed initiative

**ctx-mgmt-demo** — see
[`initiatives/_archive/2026-05-ctx-mgmt-demo/`](./initiatives/_archive/2026-05-ctx-mgmt-demo/).

| | |
|---|---|
| Period | <start>-<end> |
| Milestones | M1 -> M{N} |
| Final commit | `<sha>` |
| pytest | <before> -> <after> |
| mypy + ruff | <status> |
| English review | [`REVIEW.md`](./initiatives/_archive/2026-05-ctx-mgmt-demo/REVIEW.md) |
| Owner brief 中文 | [`OWNER_BRIEF.zh-CN.md`](./initiatives/_archive/2026-05-ctx-mgmt-demo/OWNER_BRIEF.zh-CN.md) |

## How to start a new initiative

<copy verbatim from prior NOW.md>
```

## Step 8: Update `initiatives/README.md`

Move the row for this initiative from the Active table to the Archived
table. Fill:

* final commit
* period
* milestone count
* archive path
* review link
* owner brief link, if the table structure supports it

If the current table has no owner brief column and adding one would be a
subjective schema change, do not rewrite the table. Instead, include the
owner brief path in the archived row's notes/status field if available.
If that is not possible, leave the table structure unchanged and mention
this as a Tier C proposal in `REVIEW.md` if it matters.

## Step 9: Write `review.log`

Write a terse session summary to:

```text
initiatives/_archive/2026-05-ctx-mgmt-demo/logs/review.log
```

Use this content shape and fill actual values:

```markdown
Phase 2B + 2C complete (staged multi-agent review-and-repair flow). Summary:

- **All N milestones verified**: `[ctx-demo/M1]` (`<sha>`), ...
- **Initial quality gates**: pytest <N>, mypy <status>, ruff <status>
- **Stage A subagents spawned in parallel**: code-reviewer + doc-curator-candidate-finder
- **Main-agent reconciliation completed**: <N> code findings retained, <N> doc candidates applied/downgraded/skipped
- **Review-time repair loop**: <N> findings fixed, <N> deferred
- **Review-time commits**: <list commits or "none">
- **Final quality gates green**: pytest <N> (+<delta> from <baseline>), mypy clean, ruff clean
- **Stage B narrator spawned after repair/re-review**: demo-narrator
- **REVIEW.md**: scorecards, reconciled findings, fixed-during-review ledger, deferred follow-ups, validation results, wrap-up actions
- **OWNER_BRIEF.zh-CN.md**: delivered features, demo commands, Before/After, owner-facing findings, resume/interview talking points
- **Tier A auto-applied/fixed**: <one line per edit/fix, or "none">
- **Tier B auto-applied/fixed**: <one line per edit/fix, or "none">
- **Tier C auto-applied/fixed/proposed**: <one line per edit/fix/proposal, or "none">
- **Archive committed** as `<wrap-sha> [ctx-demo/wrap]`
- **Final HEAD**: `<wrap-sha>`
- **All wrap-gate checks pass**
- **Main session stayed alive on --remote-control** for user attach.

Key audit findings and review-time outcomes:
- <up to 5 bullets from fixed or deferred findings>
```

Then stage it explicitly:

```bash
git add initiatives/_archive/2026-05-ctx-mgmt-demo/logs/review.log
```

## Step 10: Commit

Stage every path Phase 2C wrap + review-time documentation edits may have
touched. Use explicit paths. Project convention: no `git add -A`.

Review-time code/test/doc repair commits, if any, should already have
been committed before Phase 2C as `[ctx-demo/review-fix]` or
`[ctx-demo/review-doc]`. Do not squash those repair commits into
the wrap commit. The wrap commit archives and summarizes the repaired
final state.

```bash
cd python-replica

git add initiatives/                  # archived initiative + new current/.gitkeep + index + REVIEW.md + OWNER_BRIEF.zh-CN.md + review.log
git add NOW.md                        # rewritten by Step 7
git add CLAUDE.md README.md           # doc edits may have appended; no-op if untouched
git add docs/                         # subsystem docs / ADRs / DECISIONS dir may have changed

git commit -m "[ctx-demo/wrap] post-execution review + archive (review-and-repair)

REVIEW.md          : initiatives/_archive/2026-05-ctx-mgmt-demo/REVIEW.md
OWNER_BRIEF.zh-CN  : initiatives/_archive/2026-05-ctx-mgmt-demo/OWNER_BRIEF.zh-CN.md
Final pytest       : <count>. mypy + ruff clean.
Review flow        : code-reviewer + doc-curator-candidate-finder, reconciled and repaired by main agent, then demo-narrator.
"
```

After commit, verify the working tree is clean:

```bash
if [ -n "$(git status --short)" ]; then
  echo "ERROR: working tree dirty after wrap commit:"
  git status --short
  echo "Some review-time or Phase 2C edits were not staged. Add them and amend, or"
  echo "investigate which review/repair/wrap action produced unstaged changes."
  exit 1
fi
```

Verify final HEAD is the wrap commit:

```bash
if ! git log --oneline -1 | grep -qF "[ctx-demo/wrap]"; then
  git log --oneline -8
  echo "ERROR: final HEAD is not [ctx-demo/wrap]"
  exit 1
fi
```

Verify any review-time commits before wrap use allowed prefixes:

```bash
WRAP_COMMIT="$(git log --format='%H %s' | grep -F "[ctx-demo/wrap]" | head -n 1 | awk '{print $1}')"
PRE_WRAP_SUBJECTS="$(git log --format='%s' 9ba662bf65e45d08949d4524203773a63bf36902.."${WRAP_COMMIT}^" 2>/dev/null || true)"

if [ -n "$PRE_WRAP_SUBJECTS" ]; then
  INVALID_REVIEW_SUBJECTS="$(
    printf '%s\n' "$PRE_WRAP_SUBJECTS" \
      | while IFS= read -r subject; do
          case "$subject" in
            "[ctx-demo/M"*) ;;
            "[ctx-demo/review-fix]"*) ;;
            "[ctx-demo/review-doc]"*) ;;
            *) printf '%s\n' "$subject" ;;
          esac
        done
  )"

  if [ -n "$INVALID_REVIEW_SUBJECTS" ]; then
    printf '%s\n' "$INVALID_REVIEW_SUBJECTS" >&2
    echo "ERROR: initiative commits before wrap must be milestones or review-time commits"
    exit 1
  fi
fi
```

## Step 11: Stay alive on `--remote-control`

After the wrap-gate verifies, print **exactly** this line to stdout:

```text
Review complete. OWNER_BRIEF.zh-CN.md is at initiatives/_archive/2026-05-ctx-mgmt-demo/OWNER_BRIEF.zh-CN.md. Attach to this session via your browser extension or Claude desktop app to ask follow-up questions in any language, or /exit to end this session.
```

Then **wait**.

Do **NOT** call `/exit`.
Do **NOT** print a final summary that signals the task is finished.
Do **NOT** call any tool whose only purpose is to end the session.
The session must stay on `--remote-control` until the user types `/exit`.

When the user attaches and asks a question:

* Use read-only tools such as Read, Grep, Bash, git diff, and git show to
  gather evidence.
* Answer in the language the user uses. Chinese is the default for this
  initiative because the owner brief is Chinese.
* Cite files, commits, and commands wherever useful.
* After answering, wait again. Do not volunteer unnecessary next steps.

When the user types `/exit`, the session terminates and the shell
script's outer `if ! claude --remote-control ... ; then die ...; fi`
continues. The review-and-repair wrap-gate has already been verified by Step 6-10,
so the script should record a successful exit.
