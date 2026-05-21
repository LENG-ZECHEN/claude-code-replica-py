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
| Divergence discipline | Are divergences clearly explained in HANDOFF Section 3? |
| Log cleanliness | Any unexplained errors / warnings / retries in the log? |

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

## Phase 2B-6: Proposed project-doc edits
<numbered list from Step 6, with concrete file + line + diff>

## Phase 2C: Wrap-up actions taken
<list what you did in Phase 2C, with commands>
```

### Step 6: Propose project-doc edits

Run:
```
git -C python-replica diff <bootstrap-commit>..HEAD -- src/ pyproject.toml
```

(`<bootstrap-commit>` is the commit immediately BEFORE the first
`[{{COMMIT_PREFIX}}/M1]` commit. Use `git log` to locate it.)

Detect:
- New public symbols (classes, functions, CLI flags, slash commands,
  env vars, entry points) → propose `CLAUDE.md` edit (per-file summary
  update).
- New dependency in `pyproject.toml` → propose `README.md` Setup edit.
- New `simple-agent <subcommand>` surface → propose `README.md` Console
  scripts edit.

DO NOT apply these edits. Present them as a numbered list in REVIEW.md
"Proposed project-doc edits". The human reviewer applies (or rejects)
them after reading the review.

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
