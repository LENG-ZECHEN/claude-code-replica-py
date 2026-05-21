# RUNBOOK — initiative operations

This file is the **single source of truth** for how a new initiative is
bootstrapped, executed, reviewed, and archived in this repo. Anyone (human
or Claude session) who wants to start, run, or finish an initiative reads
this file first.

There are exactly **two user-triggered phases**:

| Phase | Trigger | Who does it |
|---|---|---|
| **Phase 1 — Bootstrap** | You say to a Claude session: **"Run RUNBOOK Phase 1."** | One interactive Claude session |
| **Phase 2 — Execute + Review + Wrap-up** | You run `./automation/scripts/run_all_milestones.sh` | The script (which spawns N+1 `claude --print` sessions: one per milestone, plus one final review) |

Phase 2 is fully automatic once you start it. There is no Phase 3.

---

## Conventions

### Paths

| Path | Purpose |
|---|---|
| `automation/INBOX.md` | You write the initiative brief here. Phase 1 consumes it. |
| `automation/RUNBOOK.md` | This file. |
| `automation/templates/*.md` | Skeletons Phase 1 instantiates. |
| `automation/scripts/run_all_milestones.sh` | Phase 2 entry point. |
| `automation/scripts/run_next.sh` | Single-milestone debug runner (manual). |
| `automation/logs/` | Empty in the repo; per-initiative logs go under `initiatives/current/logs/` and move to archive on wrap-up. |
| `initiatives/current/` | The active initiative lives here. Empty (`.gitkeep` only) when nothing is active. |
| `initiatives/current/PLAN.md` | The brief (originally from `INBOX.md`). |
| `initiatives/current/config.yaml` | Machine-readable milestone table. |
| `initiatives/current/HANDOFF.md` | Cross-milestone state hand-off. Rewritten by each milestone. |
| `initiatives/current/PROGRESS.md` | Append-only per-milestone log. |
| `initiatives/current/prompts/M{N}.md` | Pre-written per-milestone prompts (Phase 1 produces them). |
| `initiatives/current/logs/M{N}.log` | Raw `claude --print` output of milestone M{N}. |
| `initiatives/current/REVIEW.md` | Post-execution audit (Phase 2 review step). |
| `initiatives/_archive/<slug>/` | Completed initiative (whole `current/` folder moved here on wrap-up). |
| `NOW.md` | Single-page pointer. Rewritten by Phase 1 and by Phase 2 wrap-up. |

### Naming

- Initiative slug: short kebab-case (e.g. `mcp-integration`, `vector-memory`).
- Archive folder: `<YYYY-MM>-<slug>` (e.g. `2026-06-mcp-integration`). The
  date is the month the initiative is **bootstrapped**, not the month it
  ships.
- Commit prefix: chosen by you (`commit_prefix` in INBOX YAML). Commit
  subject for each milestone is `[<commit_prefix>/<M_ID>] <one-line>`.
  Example: `[mcp-int/M2] tool routing through ToolRegistry`. The
  exit-gate check in `run_all_milestones.sh` greps for
  `[<commit_prefix>/<M_ID>]` in the most recent commit subject.

### INBOX YAML schema (required)

```yaml
---
slug: <kebab-case>             # required, [a-z0-9-]+
commit_prefix: <short token>   # required, used in commit subjects
milestones:                    # required, at least one entry
  M1:                          # key must match ^M[0-9]+$
    name: <short title>        # required
    phase_ids: [<id>, ...]     # required, free-form labels
    exit_gate: <string>        # required, what must be true to commit
    notes: |                   # optional, free-form
      ...
  M2:
    ...
---
```

Anything after the closing `---` is free-form markdown (Goal, Design,
Risks, Out-of-scope, etc.). Phase 1 preserves it verbatim into PLAN.md.

---

## Phase 1 — Bootstrap

**Trigger:** A human types one of these phrases to a Claude session:
- "Run RUNBOOK Phase 1."
- "Bootstrap a new initiative."
- "按 RUNBOOK Phase 1 引导。" (Chinese)

The session SHOULD verify it is in `/Users/leng/my-cc-py/python-replica`
and that `automation/INBOX.md` has content beyond the placeholder header.
If either fails, refuse and explain.

### Pre-flight checks

1. Working tree is clean (`git -C python-replica status --short` empty).
2. `initiatives/current/` contains only `.gitkeep` (no active initiative).
3. `automation/INBOX.md` exists and is not the bare template
   (look for at least one milestone entry).

If any check fails, stop and report. Do not proceed.

### Steps (11)

| # | Action | Output |
|---|---|---|
| 1 | **Validate INBOX.** Parse YAML front-matter. Check `slug` matches `^[a-z0-9-]+$`, `commit_prefix` is non-empty, every milestone has `name + phase_ids + exit_gate`. | pass/fail |
| 2 | **Derive archive slug** = `<YYYY-MM>-<slug>` from today's date. | `archive_slug` |
| 3 | **Decide if `run_all_milestones.sh` needs updating** (it currently reads `config.yaml` so most changes need no script edit; only edit if your INBOX needs a feature the script doesn't yet support — extremely rare). | edit or noop |
| 4 | **Move INBOX into the initiative.** `git mv automation/INBOX.md initiatives/current/PLAN.md`. Edit `PLAN.md` to prepend a provenance header above the original `---` YAML block: `> Bootstrapped on YYYY-MM-DD. Baseline commit: <SHA>. Baseline pytest: <N> passing.` | `initiatives/current/PLAN.md` |
| 5 | **Generate `config.yaml`** from PLAN's YAML front-matter. Include `slug`, `commit_prefix`, `archive_slug`, and the full `milestones` table. | `initiatives/current/config.yaml` |
| 6 | **Write `HANDOFF.md`** using `automation/templates/handoff_initial.md`. Fill `slug`, baseline commit/pytest/mypy/ruff, first milestone's name. | `initiatives/current/HANDOFF.md` |
| 7 | **Write `PROGRESS.md`** using `automation/templates/progress_entry.md` as the file header (no milestone entries yet). | `initiatives/current/PROGRESS.md` |
| 8 | **Write per-milestone prompts.** For every M{N} in PLAN's `milestones` block, write `initiatives/current/prompts/M{N}.md` using `automation/templates/milestone_prompt.md` as a skeleton. Customize every section using PLAN content, INBOX `notes`, and CLAUDE.md execution rules. Each prompt MUST include sections §1 Baseline, §2 Scope, §3 Mandatory reading, §4 Implementation requirements, §5 Exit ritual. | N files |
| 9 | **Reset `automation/INBOX.md`** to the blank template (`automation/templates/inbox.md`). This is the file you'll edit next time. | reset INBOX |
| 10 | **Rewrite `NOW.md`** to reflect the new active initiative (slug, milestone count, planned exit, recent archive entries). | rewritten `NOW.md` |
| 11 | **Append index row** to `initiatives/README.md` Active table. | updated index |

### Phase 1 report (mandatory)

After step 11, the session reports back to the user with:

- The full list of files created/edited, with line counts.
- A summary table of the milestones from `config.yaml`.
- The exact next command: `./automation/scripts/run_all_milestones.sh`.
- A reminder that the session has NOT committed — the user reviews and
  commits when ready (commit is on the user, not the bootstrap agent).

The Phase 1 agent does NOT run `git commit`. The user commits the
bootstrap as a single change after reviewing.

---

## Phase 2 — Execute + Review + Wrap-up

**Trigger:** You run `./automation/scripts/run_all_milestones.sh` from
`python-replica/` (or any descendant — the script `cd`s to its own
location).

The script does three things in sequence:

### Phase 2A — Execute milestones (script-driven)

```
read initiatives/current/config.yaml
for each milestone M{N} in milestones (in declaration order):
    log_file = initiatives/current/logs/M{N}.log
    prompt   = initiatives/current/prompts/M{N}.md
    claude --print --model claude-opus-4-7 \
           --allowedTools "<whitelist>" --disallowedTools "<denylist>" \
           < $prompt 2>&1 | tee $log_file
    exit_gate = "[<commit_prefix>/M{N}]"
    if git log -1 | grep -qE "$exit_gate" :
        continue
    else:
        report failure with last 50 lines of log
        exit non-zero  # halts loop; subsequent milestones NOT run
```

Each milestone prompt (written in Phase 1) ends with a §5 Exit Ritual
that REQUIRES the agent to:

1. Verify the milestone's `exit_gate` (per config.yaml).
2. Commit with `[<commit_prefix>/M{N}]` subject.
3. Append a milestone block to `initiatives/current/PROGRESS.md`.
4. Rewrite `initiatives/current/HANDOFF.md` so M{N+1} can read it.
5. (last milestone only) Mark `initiatives/current/PLAN.md` STATUS as
   `complete`.

If a milestone agent fails to honor the exit ritual, the script's
`exit_gate` grep fails and the loop halts.

### Phase 2B — Review (script-spawned final claude session)

After the last milestone's exit gate passes, the script spawns ONE more
`claude --print` session whose prompt is `automation/templates/review.md`
(with the initiative path substituted in). That session does:

| # | Action |
|---|---|
| 1 | Verify every M{N} in config.yaml has a matching commit. |
| 2 | Run `pytest --tb=no -q`, `mypy src`, `ruff check .` — record final numbers. |
| 3 | **Review prompts.** Open each `initiatives/current/prompts/M{N}.md` and score on 5 dimensions: clarity, completeness, scope alignment with PLAN, constraint specificity, exit-ritual correctness. Produce a per-prompt scorecard. |
| 4 | **Review execution.** For each milestone, look at: commit message quality, test count delta, mypy/ruff status delta, number of divergences in HANDOFF Section 3, anomalies in the milestone log. Produce a per-milestone scorecard. |
| 5 | Write `initiatives/current/REVIEW.md` containing both scorecards plus a lessons-learned section that future Phase 1 bootstraps can read. |
| 6 | **Diff-driven project doc proposals.** `git diff <bootstrap-commit>..HEAD -- src/ pyproject.toml`. Detect: new public symbols, new CLI flags, new entry points, new dependencies, new env vars. Propose specific edits to `CLAUDE.md` (architecture / per-file summary) and `README.md` (commands / setup) as a numbered list inside `REVIEW.md`. Do NOT apply automatically. |

### Phase 2C — Wrap-up (same review session, after producing REVIEW.md)

| # | Action |
|---|---|
| 7 | `git mv initiatives/current initiatives/_archive/<archive_slug>` |
| 8 | `mkdir initiatives/current && touch initiatives/current/.gitkeep` (recreate empty active slot) |
| 9 | Rewrite `NOW.md` to: no active initiative, most recent archive = this one with final numbers. |
| 10 | Update `initiatives/README.md`: move the row from Active to Archived; set final commit + period. |
| 11 | Commit everything (review report + archive move + NOW/README updates) as a single `[<commit_prefix>/wrap] post-execution review + archive` commit. |

### Phase 2 report

The script tails the final review session's last 60 lines and exits with
status 0 on success. The user reads `initiatives/_archive/<slug>/REVIEW.md`
to see what passed, what scored low, and the proposed CLAUDE/README edits.

The user applies (or rejects) those proposed edits themselves — Phase 2
intentionally does NOT modify CLAUDE.md/README.md without human review.

---

## Failure modes (and recovery)

| Symptom | Cause | Recovery |
|---|---|---|
| Phase 1 refuses with "INBOX is the bare template" | You forgot to fill in INBOX | Edit `automation/INBOX.md`, retry |
| Phase 1 refuses with "working tree dirty" | Uncommitted changes | `git stash` or commit; retry |
| Phase 1 refuses with "initiatives/current/ not empty" | Previous initiative wasn't wrapped up | Either resume by running the script, or manually run Phase 2C steps |
| Script halts: "M{N} did not produce expected commit" | The milestone agent skipped its exit ritual | Read `initiatives/current/logs/M{N}.log`, fix manually or restart from M{N} with `./automation/scripts/run_next.sh M{N}` |
| Script finishes but no REVIEW.md | Review session failed | Read last log; manually invoke the review prompt against `initiatives/current/` |
| `pytest` regression at review time | A milestone introduced a real bug | Stop, investigate, fix on a branch; do NOT proceed to wrap-up until green |

---

## What this RUNBOOK does NOT cover

- The actual content of milestone prompts (that's
  `automation/templates/milestone_prompt.md` plus per-initiative
  customization by Phase 1).
- The project's coding conventions (those live in `CLAUDE.md`).
- How to install Claude Code CLI or grant `--allowedTools` permission
  (that's `automation/README.md`).
- How to write a good INBOX brief (that's documented inline in
  `automation/INBOX.md` / `automation/templates/inbox.md`).
