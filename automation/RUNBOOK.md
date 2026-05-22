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

The session MUST verify it is in `/Users/leng/my-cc-py/python-replica`
(or that `python-replica/` exists relative to the cwd) and that
`automation/INBOX.md` has content beyond the placeholder `> placeholder:`
line. If either fails, refuse and explain — do NOT proceed to Step 1.

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
| 3 | **Decide if `run_all_milestones.sh` needs updating.** Edit ONLY if (a) the INBOX YAML schema introduces a field the script must parse (e.g., a new `before_first_milestone` hook), OR (b) the script's hard-coded `CLAUDE_MODEL` / `ALLOWED_TOOLS` / `DISALLOWED_TOOLS` need changing for this initiative. Otherwise: noop. | edit or noop |
| 4 | **Move INBOX into the initiative.** `git mv automation/INBOX.md initiatives/current/PLAN.md`. Edit `PLAN.md` to prepend a provenance header above the original `---` YAML block: `> Bootstrapped on YYYY-MM-DD. Baseline commit: <SHA>. Baseline pytest: <N> passing.` | `initiatives/current/PLAN.md` |
| 5 | **Generate `config.yaml`** from PLAN's YAML front-matter. Include `slug`, `commit_prefix`, `archive_slug`, and the full `milestones` table. | `initiatives/current/config.yaml` |
| 6 | **Write `HANDOFF.md`** using `automation/templates/handoff_initial.md`. Fill `slug`, baseline commit/pytest/mypy/ruff, first milestone's name. | `initiatives/current/HANDOFF.md` |
| 7 | **Write `PROGRESS.md`** using `automation/templates/progress_entry.md` as the file header (no milestone entries yet). | `initiatives/current/PROGRESS.md` |
| 8 | **Write per-milestone prompts.** For every M{N} in PLAN's `milestones` block, write `initiatives/current/prompts/M{N}.md` using `automation/templates/milestone_prompt.md` as a skeleton. Customize every section using PLAN content, INBOX `notes`, and CLAUDE.md execution rules. Each prompt MUST include sections **§1 Baseline, §2 Scope, §2.5 Out of scope, §3 Mandatory reading, §4 Implementation requirements, §5 Exit ritual** (§2.5 is REQUIRED — the template fails open if missing). | N files |
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
    if an existing [<commit_prefix>/M{N}] commit already passes the
       resumability checks (HANDOFF touched in that commit, PROGRESS
       block present, pytest green, HANDOFF has the 5-section structure):
        skip M{N} and continue

    claude --print --model claude-opus-4-7 \
           --allowedTools "<whitelist>" --disallowedTools "<denylist>" \
           < $prompt 2>&1 | tee $log_file

    # 5-check exit gate for freshly run milestones (ALL must pass):
    1. git log -1 subject matches [<commit_prefix>/M{N}]
    2. initiatives/current/HANDOFF.md was modified in that commit
       (proves exit ritual step 4 ran)
    3. initiatives/current/PROGRESS.md contains a milestone heading
       matching the regex: ^## M{N} — done YYYY-MM-DD
       (proves exit ritual step 3 ran; anchored regex so M1 does not
       match M10/M11 and a stray "M1" string in notes does not pass)
    4. pytest --tb=no -q is green (trust-but-verify; skippable with
       --skip-quality)
    5. initiatives/current/HANDOFF.md contains the required 5-section
       structure (verbatim header match for all 5):
         ## 1. Current initiative
         ## 2. Completed milestones
         ## 3. Current repo state
         ## 4. Important constraints
         ## 5. Next milestone guidance
       (proves the agent used the structured handoff_milestone.md
       template rather than a free-form HANDOFF)
```

Each milestone prompt (written in Phase 1) ends with a §5 Exit Ritual
that REQUIRES the agent to:

1. Verify the milestone's `exit_gate` (per config.yaml) objectively —
   quote the verifying command's output, not "feels complete".
2. Commit with `[<commit_prefix>/M{N}]` subject.
3. Append a milestone block to `initiatives/current/PROGRESS.md`
   (terse-fact-log format — see `automation/templates/progress_entry.md`).
4. Rewrite `initiatives/current/HANDOFF.md` using the 5-section
   structure in `automation/templates/handoff_milestone.md` so M{N+1}
   can read it. Section 4 "Important constraints" propagates invariants;
   Section 5 "Next milestone guidance" is written FOR the next agent.
5. (last milestone only) Mark `initiatives/current/PLAN.md` STATUS as
   `complete`.

If a milestone agent fails any of the 5 exit-gate checks above, the
loop halts and subsequent milestones do NOT run. The failure message
names which check failed so you can fix and resume with
`./automation/scripts/run_next.sh M{N} --run`, then rerun
`./automation/scripts/run_all_milestones.sh`. The full loop skips
already-completed milestones that still pass the resumability checks and
continues at the next incomplete milestone.

### HANDOFF vs PROGRESS — responsibility split

These two files look similar but serve different audiences. Keep them
in their lanes to avoid duplication and rot.

| File | Audience | Format | Update mode | Purpose |
|---|---|---|---|---|
| `initiatives/current/HANDOFF.md` | The NEXT milestone agent | 5-section structured (narrative allowed) | Rewritten each milestone | Cross-milestone state baton — design decisions, invariants, next-milestone guidance |
| `initiatives/current/PROGRESS.md` | The final REVIEW agent | Terse bullets per block | Append-only | Cross-milestone fact log — commit, tests delta, files, exit-gate evidence |

If you feel an entry could go in either, ask:
- "Does the next milestone agent need this to do their job?" → HANDOFF
- "Does the final review need this to audit what happened?" → PROGRESS
- Both? → put the narrative in HANDOFF and the bullet in PROGRESS.

### Phase 2B — Review (script-spawned final claude session)

After the last milestone's exit gate passes, the script spawns ONE more
`claude --print` session whose prompt is `automation/templates/review.md`
(with the initiative path substituted in). That session does:

| # | Action |
|---|---|
| 1 | Verify every M{N} in config.yaml has a matching commit. |
| 2 | Run `pytest --tb=no -q`, `mypy src`, `ruff check .` — record final numbers. |
| 3 | **Review prompts.** Open each `initiatives/current/prompts/M{N}.md` and score on **8 dimensions** (clarity, completeness, scope alignment with PLAN, constraint specificity, exit-ritual correctness, out-of-scope enumeration, mandatory-reading completeness, exit-gate objectivity) — see `automation/templates/review.md` Step 3 for the full table. Produce a per-prompt scorecard. |
| 4 | **Review execution.** For each milestone, look at: commit message quality, test count delta, mypy/ruff status delta, **design decisions in the milestone's HANDOFF Section 2 subsection**, anomalies in the milestone log, plus 4 audit dimensions (implementation matches PLAN, scope discipline, HANDOFF accuracy, failure-path coverage) — see `automation/templates/review.md` Step 4 for the full table. Produce a per-milestone scorecard with **9 dimensions**. |
| 5 | Write `initiatives/current/REVIEW.md` containing both scorecards plus a lessons-learned section that future Phase 1 bootstraps can read. |
| 6 | **Three-tier doc update.** Diff `<bootstrap-commit>..HEAD -- src/ pyproject.toml` then act per the **Doc-update tiers** subsection below: A-tier safe edits applied automatically, B-tier judged-creations applied automatically when triggers match, C-tier rewrites only proposed in REVIEW.md. Every applied edit is logged in REVIEW.md's `## Auto-applied edits` section. |

### Doc-update tiers (used by Step 6)

The review agent classifies every doc-change candidate into one of three
tiers and acts differently per tier. The bias is **moderately
aggressive**: when a trigger is reasonably close to one of the rules
below, prefer to act over propose. The wrap-up commit is one atomic
unit, so an over-eager edit is easy to revert in one `git revert`.

**Important exception — Tier A is NOT subject to the moderately-aggressive
bias.** For Tier A, "unsure whether this is mechanical enough" means
the edit is not actually mechanical and should be downgraded to Tier C
(propose only). The bias applies to Tier B only (where the action is
"create a new file", which is cheap to revert by `git rm`).

#### Tier A — safe auto-apply (always apply when triggered)

Mechanical, append-only operations on existing files. The review agent
applies these without asking and logs each in REVIEW.md `## Auto-applied
edits`.

| Trigger | Action |
|---|---|
| `src/` has a new `.py` file with at least one public symbol that is not yet in `CLAUDE.md`'s per-file summary table | Append a new "### `<filename>`" section to CLAUDE.md per-file summaries, mirroring the existing format. |
| `pyproject.toml` `[project.scripts]` has a new entry not in `README.md`'s Console scripts table | Append a row to that table. |
| `pyproject.toml` `[project] dependencies` has a new entry | Append a one-line note under README.md Setup. |
| A new CLI flag is added to an existing entry-point CLI (visible in `--help`) | Append it to README.md's relevant flag list. |

Hard rules for Tier A:
- **APPEND only** — never edit existing rows / paragraphs / bullets.
- **Never delete** any line.
- **Never touch** the first 10 lines of README.md (elevator pitch) or the
  "Implementation Roadmap (Completed P1–P8)" section of CLAUDE.md.

#### Tier B — judged auto-apply (apply when triggers match, with moderate aggression)

Creating new files. Requires a clear trigger but is acceptable to apply
without human approval because new files are easier to delete than edits
to existing files are to revert.

| Trigger | Action |
|---|---|
| `src/` gains a new **subdirectory**, OR a new top-level module that is **>150 LOC** AND exports **≥3 public symbols** (non-underscored functions/classes/dataclasses) | Create `docs/<slug>.md` using `automation/templates/subsystem_doc.md`. If `docs/<slug>.md` already exists, **append** a "## Recent changes" bullet instead. |
| HANDOFF.md Section 2's per-milestone "design decisions (deviations from PLAN)" subsections **collectively contain ≥2 divergences** AND at least one is architectural (keywords: `renamed module`, `new abstraction`, `dropped feature`, `protocol change`, `inverted dependency`), OR a single divergence touches **>2 source files** | Create `docs/DECISIONS/<NNNN>-<slug>.md` using `automation/templates/adr.md`. If `docs/DECISIONS/` doesn't exist yet, create it with a `README.md` index file too. NNNN = (max existing) + 1, zero-padded to 4 digits, starting at 0001. |

Hard rules for Tier B:
- **Never overwrite** an existing file at the target path. If it exists,
  fall back to Tier A append (or, if the file is not append-friendly,
  drop to Tier C propose).
- Every B-tier creation is logged in REVIEW.md `## Auto-applied edits`
  with the exact trigger that fired.
- If unsure whether a trigger has fired, **prefer to apply** (moderate
  aggression). Over-eager B-tier writes are reversible by deleting the
  one new file.

#### Tier C — propose only (never auto-apply)

Anything that would rewrite existing prose, change existing rows in
tables, delete content, or reorganize file structure. These go into
REVIEW.md `## Proposed edits (need human review)` as a numbered list.

| Trigger | Why Tier C |
|---|---|
| An existing CLAUDE.md per-file summary needs paraphrasing because the module's behavior fundamentally changed | Rewrites risk losing carefully chosen wording |
| README.md Setup section needs reorganization | Affects elevator pitch + first-impression |
| Existing ADR superseded by this initiative | Requires Status-line edit on the old ADR — human should confirm reasoning |
| Existing `docs/<subsystem>.md` overview section appears stale | "Stale" judgment is subjective; let human decide |

### Phase 2C — Wrap-up (same review session, after producing REVIEW.md)

| # | Action |
|---|---|
| 7 | `git mv initiatives/current initiatives/_archive/<archive_slug>` |
| 8 | `mkdir initiatives/current && touch initiatives/current/.gitkeep` (recreate empty active slot) |
| 9 | Rewrite `NOW.md` to: no active initiative, most recent archive = this one with final numbers. |
| 10 | Update `initiatives/README.md`: move the row from Active to Archived; set final commit + period. |
| 11 | Commit everything (review report + archive move + NOW/README updates + any Tier A/B doc edits) as a single `[<commit_prefix>/wrap] post-execution review + archive` commit. |

After the review session exits, the shell script enforces a **6-check
wrap gate**:

1. latest commit subject contains `[<commit_prefix>/wrap]`
2. `initiatives/_archive/<archive_slug>/` exists
3. `initiatives/_archive/<archive_slug>/REVIEW.md` exists
4. `initiatives/current/.gitkeep` exists
5. `initiatives/current/` contains no files other than `.gitkeep`
6. `git status --short` is empty, proving Tier A/B edits were staged
   into the wrap commit rather than left behind

### Phase 2 report

The script tails the archived final review session log's last 60 lines
when that log exists, then exits with status 0 on success. The user reads
`initiatives/_archive/<slug>/REVIEW.md`
to see what passed, what scored low, **which Tier A/B doc edits were
auto-applied**, and which Tier C edits still need human review.

Tier A/B edits may already have been applied by the review session (per
"Doc-update tiers" above). Tier C edits are NEVER applied automatically;
the user applies or rejects them after reading `REVIEW.md`. The
distinction is enforced by the review session's behavior, not by Phase 2C
itself — Phase 2C only handles archive + NOW.md + index updates.

---

## Failure modes (and recovery)

| Symptom | Cause | Recovery |
|---|---|---|
| Phase 1 refuses with "INBOX is the bare template" | You forgot to fill in INBOX | Edit `automation/INBOX.md`, retry |
| Phase 1 refuses with "working tree dirty" | Uncommitted changes | `git stash` or commit; retry |
| Phase 1 refuses with "initiatives/current/ not empty" | Previous initiative wasn't wrapped up | Either resume by running the script, or manually run Phase 2C steps |
| Phase 1 crashed mid-bootstrap (partial state: INBOX moved but PLAN/config/HANDOFF/prompts incomplete) | Phase 1 Step 4+ failed after `git mv automation/INBOX.md initiatives/current/PLAN.md` succeeded | **Recovery (do not retry blindly — pre-flight will refuse both ways):** (1) inspect: `ls initiatives/current/`; (2) restore INBOX: `git -C python-replica restore --source=HEAD --staged --worktree automation/INBOX.md` (assumes the `git mv` was never committed — if it was, use `git show HEAD~1:automation/INBOX.md > automation/INBOX.md` against the bootstrap parent); (3) clear partial initiative: `git -C python-replica restore --staged initiatives/current/` then remove anything other than `.gitkeep`; (4) re-run Phase 1 from a clean slate |
| Script halts: "M{N} failed exit-gate check N" | The milestone agent skipped its exit ritual (check name says which step) | Read `initiatives/current/logs/M{N}.log`, fix manually or restart from M{N} with `./automation/scripts/run_next.sh M{N} --run` |
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
