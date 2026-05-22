<!--
PROMPT for the script-spawned review + wrap-up session.

automation/scripts/run_all_milestones.sh invokes one final
`claude --print` after all milestones pass their exit gate. The script
substitutes {{INITIATIVE_SLUG}}, {{COMMIT_PREFIX}}, {{ARCHIVE_SLUG}}
before piping this file as stdin.

The review session is REQUIRED to honor the steps below in order. Its
exit ritual (Phase 2C wrap-up) physically moves initiatives/current/
into initiatives/_archive/ and commits the result.

Comment blocks (HTML comments) are guidance and should NOT appear in
the final REVIEW.md.
-->

# Phase 2B + 2C — Review and wrap-up for `{{INITIATIVE_SLUG}}`

You are the **review + wrap-up agent** for the `{{INITIATIVE_SLUG}}`
initiative. Every milestone has already produced its commit; your job is
to audit prompt quality + execution quality, write a single REVIEW.md,
propose project-level doc edits, and archive the initiative folder.

There is no user available. Follow every step. Stop only on a clear
quality failure (pytest red, mypy red).

## Mandatory reading

1. `python-replica/automation/RUNBOOK.md` — your role is documented in
   Phase 2B + 2C.
2. `python-replica/initiatives/current/PLAN.md` — the original brief.
3. `python-replica/initiatives/current/config.yaml` — milestone table.
4. Every `python-replica/initiatives/current/prompts/M{N}.md` —
   the per-milestone prompts you are auditing.
5. Every `python-replica/initiatives/current/logs/M{N}.log` —
   the raw run logs.
6. `python-replica/initiatives/current/HANDOFF.md` — terminal state
   (rewritten by the last milestone).
7. `python-replica/initiatives/current/PROGRESS.md` — per-milestone log.

## Phase 2B — Review steps

### Step 1: Verify completion

For every M{N} in `config.yaml`:
- `git -C python-replica log --oneline | grep -F "[{{COMMIT_PREFIX}}/M{N}]"`
  must return at least one match.
- If any milestone is missing its commit, STOP and write a
  REVIEW.md with just a "BLOCKED" section explaining which milestone
  failed and why. Skip Steps 2-7 and Phase 2C.

### Step 2: Snapshot final numbers

```
cd python-replica
pytest --tb=no -q       # record total passing
mypy src/               # record status
ruff check .            # record status
```

If pytest is red OR mypy is red OR ruff is red, STOP. The initiative
cannot be wrapped up while quality gates are broken. Write a REVIEW.md
with just a "BLOCKED" section quoting the failing output.

### Step 3: Prompt quality scorecard (per milestone)

For each `prompts/M{N}.md` score on 5 dimensions (1-5 each):

| Dimension | What to look for |
|---|---|
| Clarity | Can a fresh session execute this without ambiguity? |
| Completeness | Are §1-§5 all present and substantively filled? |
| Scope alignment | Do the §2 scope + exit gate match PLAN's M{N} entry? |
| Constraint specificity | Are TDD / file-limit / no-`-A` requirements explicit? |
| Exit-ritual correctness | Does §5 match `automation/templates/milestone_prompt.md` §5? |
| **Out-of-scope enumeration** | Does §2.5 list concrete "do not" items (other milestones, harness files, unrelated refactors, public-API changes, new deps), or is it just a generic disclaimer? |
| **Mandatory reading completeness** | Does §3 list all 8 mandatory reads (CLAUDE.md, PLAN.md, config.yaml, HANDOFF.md, PROGRESS.md, expected files, git log when N>1, prior log when N>2)? |
| **Exit gate objectivity** | Is the exit_gate quoted in §2 objectively verifiable by a command output, NOT subjective phrasing like "implementation is good" / "looks correct"? |

Produce a markdown table inside REVIEW.md.

### Step 4: Execution quality scorecard (per milestone)

For each milestone, inspect: the commit subject, the commit body, the
test count delta (from PROGRESS.md), the mypy/ruff status delta, the
divergences listed in HANDOFF.md Section 3 across iterations, and any
anomalies in the milestone log.

Score on 5 dimensions:

| Dimension | What to look for |
|---|---|
| Commit hygiene | Subject matches `[{{COMMIT_PREFIX}}/M{N}]` format; body explains why |
| Test growth | Did pytest grow as expected? Were new tests meaningful? |
| Gate honor | mypy + ruff still clean? |
| Divergence discipline | Are divergences clearly explained in the milestone's HANDOFF Section 2 "design decisions" subsection? |
| Log cleanliness | Any unexplained errors / warnings / retries in the log? |
| **Implementation matches PLAN** | Does the diff actually deliver what PLAN.md M{N} promised, or only the surface (tests pass but the architecture / public-API shape differs from what was planned)? Quote the PLAN passage and the matching diff hunks. |
| **Scope discipline** | Did the milestone touch only files listed in its prompt §2 "Expected files to touch", or did it scope-creep into unrelated modules? Run `git show --stat <commit>` and compare with §2. |
| **HANDOFF accuracy** | Cross-reference the milestone's HANDOFF Section 2 ("behavior implemented", "files changed", "tests added") with the actual diff and PROGRESS.md entry. Does what's CLAIMED match what SHIPPED? Catch HANDOFF inflation early. |
| **Failure-path coverage** | Did new tests cover error / edge paths (look for `pytest.raises`, invalid-input cases, boundary conditions), or only happy path? A milestone whose 100% of new tests are happy-path is fragile and should be flagged. |

### Step 5: Write `initiatives/current/REVIEW.md`

Use this structure:

```
# REVIEW — {{INITIATIVE_SLUG}}

## Summary
- Initiative period: <start> → <end>
- Milestones: <count>, all complete
- pytest: <before> → <after> (Δ +N)
- mypy: <status>; ruff: <status>
- Total commits in this initiative: <N>
- Lessons learned: <bullets — what worked, what to do differently next time>

## Phase 2B-3: Prompt quality scorecards
<markdown table from Step 3>

## Phase 2B-4: Execution quality scorecards
<markdown table from Step 4>

## Auto-applied edits
<Tier A + Tier B entries from Step 6. One bullet per edit:
 - Tier A | <file> | <one-line summary> | trigger: <which row>
 - Tier B | <new file path> | <one-line summary> | trigger: <which row>
 If none were applied, write "(none — diff did not match any A/B trigger)">

## Proposed edits (need human review)
<Tier C entries from Step 6. Numbered list with file:line + suggested diff.
 If none, write "(none)">

## Phase 2C: Wrap-up actions taken
<list what you did in Phase 2C, with commands>
```

### Step 6: Three-tier doc update

Read `automation/RUNBOOK.md` section "Doc-update tiers (used by Step 6)"
in full before starting this step. The tier definitions live there; this
section just tells you how to execute them.

Run the diff once at the top of this step:

```
git -C python-replica log --oneline | grep -F "[{{COMMIT_PREFIX}}/M1]"  # find bootstrap-commit
BOOTSTRAP_PARENT=<the commit immediately before the [{{COMMIT_PREFIX}}/M1] commit>
git -C python-replica diff $BOOTSTRAP_PARENT..HEAD --stat -- src/ pyproject.toml
git -C python-replica diff $BOOTSTRAP_PARENT..HEAD --name-only -- src/ pyproject.toml
```

Then walk each tier in order:

#### Tier A — apply automatically (append only)

For each change-candidate that matches a Tier A trigger (see RUNBOOK):

1. Locate the target file + insertion point.
2. Use Edit to APPEND a row / bullet / section. Do not modify existing
   content. Do not touch the first 10 lines of README.md or the
   Implementation Roadmap section of CLAUDE.md.
3. Record what you did in REVIEW.md `## Auto-applied edits` with:
   ```
   - Tier A | <file> | <one-line summary> | trigger: <which Tier A row>
   ```

If you are unsure whether a candidate is mechanical-enough for Tier A,
downgrade it to Tier C (propose only).

#### Tier B — judged auto-apply (create new files)

Be **moderately aggressive**: when a trigger is close to firing, prefer
to act over propose. New files are reversible with a single `git rm`.

For each candidate matching a Tier B trigger:

1. **Subsystem doc** (`docs/<slug>.md`): copy
   `automation/templates/subsystem_doc.md` into place, fill every
   `{{placeholder}}`. The slug = new subdir name OR new module basename
   (kebab-case). If the file already exists, do NOT overwrite — append
   a `- {{TODAY}} — {{INITIATIVE_SLUG}} — ...` bullet to the file's
   `## Recent changes` section instead.

2. **ADR** (`docs/DECISIONS/<NNNN>-<slug>.md`):
   - If `docs/DECISIONS/` does not exist, create it AND write a
     `README.md` index with a one-line table (Number / Date / Title /
     Status / Initiative).
   - NNNN = `ls docs/DECISIONS/ | grep -E '^[0-9]{4}' | sort | tail -1
     | cut -c1-4` + 1, zero-padded to 4. Starts at `0001` for the first
     ADR ever.
   - slug = kebab-case of the divergence title (≤6 words).
   - Copy `automation/templates/adr.md` into place, fill every
     `{{placeholder}}`. Source the Context / Decision / Consequences
     fields from HANDOFF.md Section 3 verbatim where possible.
   - After creating, **append** a row to `docs/DECISIONS/README.md`'s
     index table.

3. Record EVERY B-tier creation in REVIEW.md `## Auto-applied edits`:
   ```
   - Tier B | <new file path> | <one-line summary> | trigger: <which Tier B row>
   ```

#### Tier C — propose only

For every candidate that does NOT fit Tier A or B (anything requiring a
rewrite, deletion, reorganization, or subjective "staleness" judgment),
write a numbered entry in REVIEW.md `## Proposed edits (need human review)`:

```
1. <file>:<line-or-section> — <what to change> — why: <reason>
   Suggested diff:
   ```diff
   - old line
   + new line
   ```
```

DO NOT apply Tier C edits. The human reviewer applies them after reading
the review.

## Phase 2C — Wrap-up steps

Only proceed if Step 1 passed (no BLOCKED) and Step 2 was green.

### Step 7: Archive

```
cd python-replica
git mv initiatives/current initiatives/_archive/{{ARCHIVE_SLUG}}
mkdir initiatives/current
touch initiatives/current/.gitkeep
```

### Step 8: Rewrite NOW.md

Use this template:

```
# NOW — current initiative status

## Active initiative

**None.**

`initiatives/current/` is empty (`.gitkeep` only).

## Last completed initiative

**{{INITIATIVE_SLUG}}** — see
[`initiatives/_archive/{{ARCHIVE_SLUG}}/`](./initiatives/_archive/{{ARCHIVE_SLUG}}/).

| | |
|---|---|
| Period | <start>–<end> |
| Milestones | M1 → M{N} |
| Final commit | `<sha>` |
| pytest | <before> → <after> |
| mypy + ruff | <status> |

## How to start a new initiative

(Keep the same "How to start a new initiative" section that was in the
prior NOW.md — copy verbatim.)
```

### Step 9: Update `initiatives/README.md`

Move the row for this initiative from the Active table to the Archived
table. Fill final commit, period, milestone count.

### Step 10: Commit

```
cd python-replica
git add initiatives/ NOW.md
git commit -m "[{{COMMIT_PREFIX}}/wrap] post-execution review + archive

REVIEW: initiatives/_archive/{{ARCHIVE_SLUG}}/REVIEW.md
Final pytest: <count>. mypy + ruff clean.
"
```

### Step 11: Report

Print the last 30 lines of REVIEW.md to stdout so the shell loop can
tail it. Exit 0 on success.
