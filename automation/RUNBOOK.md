# RUNBOOK — initiative operations

This file is the **single source of truth** for how a new initiative is
bootstrapped, executed, reviewed, and archived in this repo. Anyone (human
or Claude session) who wants to start, run, or finish an initiative reads
this file first.

There are exactly **two user-triggered phases**:

| Phase | Trigger | Who does it |
|---|---|---|
| **Phase 1 — Bootstrap** | You say to a Claude session: **"Run RUNBOOK Phase 1."** | One interactive Claude session |
| **Phase 2 — Execute + Review + Wrap-up** | You run `./automation/scripts/run_all_milestones.sh` | The script (which spawns N `claude --print` sessions for milestones, plus one final interactive `claude --remote-control` review session) |

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

1. Working tree has no uncommitted changes **except**
   `automation/INBOX.md`. This exception is required because the normal
   user path is to edit the tracked INBOX file before triggering Phase 1.
   Check with:
   `git -C python-replica status --short --untracked-files=all`.
   Every listed path, after the two-column status prefix, must be
   `automation/INBOX.md` (or the output is empty). `M`, `MM`, or staged
   status variants for that one path are allowed. Any other modified,
   staged, deleted, renamed, or untracked path is a hard failure.
2. `initiatives/current/` contains only `.gitkeep` (no active initiative).
3. `automation/INBOX.md` exists and is not the bare template. **Three
   hard checks** (ALL must hold):
   (a) `grep -q '^> placeholder:' automation/INBOX.md` returns
       NON-zero (the placeholder block has been deleted);
   (b) the parsed `slug` value is NOT `example-slug` (the literal
       template default);
   (c) the parsed `commit_prefix` value is NOT `example-prefix`.
   **Why not "at least one milestone entry"?** The bare template itself
   already declares example `M1` and `M2` entries, so a milestone-count
   check trivially passes and cannot tell template from real content.
   The three signals above ARE template-specific and disappear the
   moment the user replaces them with real values.
4. The `commit_prefix` declared in INBOX is NOT already used anywhere
   in git history. Check with
   `git -C python-replica log --format='%s' | grep -qF "[${commit_prefix}/"`.
   If it returns non-empty (a prior initiative already used the same
   prefix), refuse and ask the user to pick a different prefix.
   **Implementation note:** this check needs INBOX's `commit_prefix`,
   which requires YAML parsing — do the parse once here and reuse the
   parsed structure for Step 1 ("Validate INBOX") below instead of
   re-parsing. If the YAML is malformed and `commit_prefix` cannot be
   extracted, surface that as a distinct failure ("INBOX YAML parse
   error: <details>") rather than reporting "prefix already used",
   so the user knows which problem to fix first.
   **Why:** prefix reuse would let `run_all_milestones.sh`'s
   `find_milestone_commit` and the review session's Step 1 grep collide
   with prior-initiative commits, causing either misleading "PROGRESS
   block missing" failures or (in pathological cases) false skips.
   `baseline_commit` (Step 5 below) defends the runtime, but rejecting
   reuse here catches the problem earlier and avoids confusing the user.

If any check fails, stop and report. Do not proceed.

### Milestone sizing assessment (before Step 1 — mandatory)

Each milestone runs in **one** `claude --print` session. Claude Code's
auto-compaction thrash-loop protection (v2.1.89+) terminates a session
cleanly (exit 0, no `end_turn`, no commit) if the context refills to
the limit three times in a row after compaction. M1 of
`observable-thresholds` (May 2026) hit exactly this at turn 243 — 11
src files + 5 test files + a cross-cutting `Tracer` Protocol wiring
proved too heavy for one session. Source work was complete; the
commit was not. See
[anthropics/claude-code#41796](https://github.com/anthropics/claude-code/issues/41796).

**Before Step 1, parse INBOX's milestone table and flag any milestone
that hits ANY of these heuristics:**

| Signal | Threshold |
|---|---|
| Source files to touch (`src/` only, count from INBOX `notes` + Design sketch) | **> 6** |
| Components receiving a cross-cutting interface change (new Protocol, new required constructor param, new pure-function signature) | **> 4** |
| New test cases (sum across all `tests/test_*.py`) | **> 15** |
| Combines "introduce abstraction" + "wire it across N components" + "expose via CLI" in a single milestone | always — this is the M1 pattern that thrashed |

**When triggered**, the Phase 1 agent MUST:

1. **Propose a split** to the user before proceeding. A typical split
   looks like:
   - `M{N}a` — introduce the new abstraction (1-2 src files, focused
     unit tests, no migration)
   - `M{N}b` — wire the abstraction into existing components (the
     migration; touch only the components, not the CLI)
   - `M{N}c` — expose via CLI flag / integration test (the user-facing
     surface)
2. **Wait for explicit user confirmation** of the split before
   continuing. The agent does NOT auto-split — the user owns scope.
3. **If the user declines the split** (e.g. the work is genuinely
   atomic), record `> SIZING WAIVED: <user rationale>` in PLAN.md's
   provenance block alongside the baseline line, so the failure mode
   is traceable if it recurs.

This assessment is honor-system — there is no automated check. The
goal is to surface size risk at planning time rather than at turn 243.

### Steps (11)

| # | Action | Output |
|---|---|---|
| 1 | **Validate INBOX.** Parse YAML front-matter. Check `slug` matches `^[a-z0-9-]+$`, `commit_prefix` matches `^[a-z0-9][a-z0-9_-]{0,31}$` (it is interpolated unquoted into sed -E regexes in `run_all_milestones.sh`, so regex meta-chars are unsafe), every milestone has `name + phase_ids + exit_gate`. | pass/fail |
| 2 | **Derive archive slug** = `<YYYY-MM>-<slug>` from today's date. | `archive_slug` |
| 3 | **Decide if `run_all_milestones.sh` needs updating.** Edit ONLY if (a) the INBOX YAML schema introduces a field the script must parse (e.g., a new `before_first_milestone` hook), OR (b) the script's hard-coded `CLAUDE_MODEL` / `ALLOWED_TOOLS` / `DISALLOWED_TOOLS` need changing for this initiative. Otherwise: noop. | edit or noop |
| 4 | **Move INBOX into the initiative.** `git mv automation/INBOX.md initiatives/current/PLAN.md`. Edit `PLAN.md` to **insert a provenance block IMMEDIATELY AFTER the closing `---` of the YAML front-matter** (NOT before — putting it before would push `---` off line 1 and break standard frontmatter parsers): `> Bootstrapped on YYYY-MM-DD. Baseline commit: <SHA>. Baseline pytest: <N> passing.` followed by a blank line, then the free-form markdown body that came after `---` in INBOX. The resulting PLAN.md shape is: line 1 `---`, then YAML body, then `---`, then provenance block, then blank line, then PLAN's prose body. This keeps PLAN.md parseable as standard frontmatter. | `initiatives/current/PLAN.md` |
| 5 | **Generate `config.yaml`** from PLAN's YAML front-matter. Include `slug`, `commit_prefix`, `archive_slug`, `baseline_commit` (output of `git -C python-replica rev-parse HEAD` at Phase 1 entry — the same SHA recorded in PLAN.md's provenance header and HANDOFF.md Section 3 baseline), and the full `milestones` table. `baseline_commit` lets `run_all_milestones.sh` and the review session restrict every commit-subject grep to this initiative's range (`baseline_commit..HEAD`), preventing collisions with prior-initiative commits that may have reused the same `commit_prefix`. | `initiatives/current/config.yaml` |
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

> **Phase 2 pre-flight is stricter than Phase 1's.** Phase 1 allows
> `automation/INBOX.md` to be the only dirty path (the normal user
> path edits INBOX before triggering Phase 1). By the time you reach
> Phase 2, the user is expected to have committed Phase 1's bootstrap
> diff (Phase 1 itself never commits — see Step 11), so Phase 2's
> pre-flight requires a strictly clean working tree with NO
> exceptions. If Phase 2 refuses because the tree is dirty, commit or
> stash the leftover changes and retry.

The script does three things in sequence:

### Phase 2A — Execute milestones (script-driven)

```
read initiatives/current/config.yaml
for each milestone M{N} in milestones (in declaration order):
    log_file = initiatives/current/logs/M{N}.log
    prompt   = initiatives/current/prompts/M{N}.md
    if an existing [<commit_prefix>/M{N}] commit **in the range
       baseline_commit..HEAD** already passes the resumability checks
       (HANDOFF touched in that commit, PROGRESS block present, pytest
       green, HANDOFF has the 5-section structure):
        skip M{N} and continue
    (The baseline_commit..HEAD range — recorded in config.yaml by
     Phase 1 Step 5 — is what prevents a prior archived initiative that
     reused this commit_prefix from poisoning the resumability check.)

    claude --print --model claude-opus-4-7 \
           --allowedTools "<whitelist>" --disallowedTools "<denylist>" \
           < $prompt 2>&1 | tee $log_file

    # 6-check exit gate for freshly run milestones (ALL must pass):
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
    6. Append-only contract: for every prior milestone M{i} found in
       baseline_commit..HEAD (i.e. every [<commit_prefix>/M{i}] commit
       this initiative produced before the current M{N}):
         - initiatives/current/PROGRESS.md still contains a heading
           matching ^## M{i} — done YYYY-MM-DD
         - initiatives/current/HANDOFF.md still contains a Section 2
           subsection heading matching ^### M{i}$
       Without this check, a milestone agent that rewrote PROGRESS.md
       or HANDOFF.md Section 2 from scratch (erasing M1..M{N-1}'s real
       records) would slip past checks 1-5. M1 trivially passes
       because there are no prior milestones.
```

Each milestone prompt (written in Phase 1) ends with a §5 Exit Ritual
that REQUIRES the agent to:

1. Verify the milestone's `exit_gate` (per config.yaml) objectively —
   quote the verifying command's output, not "feels complete".
2. Commit with `[<commit_prefix>/M{N}]` subject.
3. **APPEND** a milestone block to `initiatives/current/PROGRESS.md`
   (terse-fact-log format — see `automation/templates/progress_entry.md`).
   Prior milestones' `## M{i} — done` blocks MUST remain verbatim;
   exit-gate check 6 enforces this.
4. Rewrite `initiatives/current/HANDOFF.md` using the 5-section
   structure in `automation/templates/handoff_milestone.md` so M{N+1}
   can read it. Section 4 "Important constraints" propagates invariants;
   Section 5 "Next milestone guidance" is written FOR the next agent.
   In Section 2 "Completed milestones", **APPEND** a new `### M{N}`
   subsection — prior `### M{i}` subsections MUST be preserved
   verbatim; exit-gate check 6 enforces this too.
5. (last milestone only) Mark `initiatives/current/PLAN.md` STATUS as
   `complete`.

If a milestone agent fails any of the 6 exit-gate checks above, the
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
interactive `claude --remote-control` session whose prompt is `automation/templates/review.md`
(with the initiative path substituted in). That session does:

| # | Action |
|---|---|
| 1 | Verify every M{N} in config.yaml has a matching commit. |
| 2 | Run `pytest --tb=no -q`, `mypy src`, `ruff check .` — record final numbers. |
| 3 | **Review prompts.** Open each `initiatives/current/prompts/M{N}.md` and score on **8 dimensions** (clarity, completeness, scope alignment with PLAN, constraint specificity, exit-ritual correctness, out-of-scope enumeration, mandatory-reading completeness, exit-gate objectivity) — see `automation/templates/review.md` Step 3 for the full table. Produce a per-prompt scorecard. |
| 4 | **Review execution.** For each milestone, look at: commit message quality, test count delta, mypy/ruff status delta, **design decisions in the milestone's HANDOFF Section 2 subsection**, anomalies in the milestone log, plus 4 audit dimensions (implementation matches PLAN, scope discipline, HANDOFF accuracy, failure-path coverage) — see `automation/templates/review.md` Step 4 for the full table. Produce a per-milestone scorecard with **9 dimensions**. |
| 5 | Write `initiatives/current/REVIEW.md` containing both scorecards plus a lessons-learned section that future Phase 1 bootstraps can read. |
| 6 | **Three-tier doc update.** Diff `baseline_commit..HEAD -- src/ pyproject.toml` (where `baseline_commit` is the field Phase 1 Step 5 wrote into `initiatives/current/config.yaml`; the shell script substitutes its concrete SHA into the review prompt as `{{BASELINE_COMMIT}}`) then act per the **Doc-update tiers** subsection below: A-tier safe edits applied automatically, B-tier judged-creations applied automatically when triggers match, C-tier rewrites only proposed in REVIEW.md. Every applied edit is logged in REVIEW.md's `## Auto-applied edits` section. |

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
| `src/` gains a new **subdirectory**, OR a new top-level module that is **>150 LOC** AND exports **≥3 public symbols** | Create `docs/<slug>.md` using `automation/templates/subsystem_doc.md`. If `docs/<slug>.md` already exists, **append** a "## Recent changes" bullet instead. |
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

**Definition: "public symbol"** for the subsystem-doc trigger above —
a top-level name in the module that is reachable as part of the
module's API surface. Concretely, the union of:
(i) names listed in the module's `__all__` (if defined); OR
(ii) when `__all__` is absent, non-underscore-prefixed `def`,
`class`, `@dataclass`, `Protocol` subclass, `TypeAlias`, and
module-level `Final[...] = ...` constants at the top level of the
file.
Imported names re-exported via `from x import y` count only when
`__all__` lists them. Anything starting with `_` is excluded.

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

The review session's live stdout is written to ignored scratch path
`automation/logs/<archive_slug>-review.log`, not to
`initiatives/current/logs/review.log`. After the 6-check wrap gate passes,
the shell script copies that finalized scratch log to
`initiatives/_archive/<archive_slug>/logs/review.log`, stages that one
file, and amends the `[<commit_prefix>/wrap]` commit when the log produced
a staged diff. It then verifies the latest commit still has the wrap
subject and that `git status --short` is empty.

### Phase 2 report

The script tails the archived final review session log's last 60 lines,
then exits with status 0 on success. The user reads
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
| Phase 1 refuses with "INBOX placeholder block still present" | Pre-flight 3(a) failed — you forgot to delete the `> placeholder:` block at the top of INBOX | Delete the entire `> placeholder:` paragraph from `automation/INBOX.md`, retry |
| Phase 1 refuses with "INBOX slug is still 'example-slug'" | Pre-flight 3(b) failed — you replaced the placeholder block but did not change the YAML slug | Edit the `slug:` value in `automation/INBOX.md` to a real kebab-case name, retry |
| Phase 1 refuses with "INBOX commit_prefix is still 'example-prefix'" | Pre-flight 3(c) failed — you changed slug but forgot commit_prefix | Edit the `commit_prefix:` value in `automation/INBOX.md` to a real short token, retry |
| Phase 1 refuses with "working tree dirty outside automation/INBOX.md" | You have uncommitted changes besides the initiative brief | Commit or stash every non-INBOX change, keep only `automation/INBOX.md` dirty, retry |
| Phase 1 refuses with "initiatives/current/ not empty" | Previous initiative wasn't wrapped up | Either resume by running the script, or manually run Phase 2C steps |
| Phase 1 refuses with "commit_prefix already used in git history" | You chose a prefix that a prior (archived) initiative already used | Edit `automation/INBOX.md` and pick a different `commit_prefix`, retry. Pre-flight check 4 enforces prefix uniqueness so `find_milestone_commit` cannot collide with prior-initiative commits |
| Script halts: "baseline_commit ... is not an ancestor of HEAD" | Branch was rebased / cherry-picked / hard-reset since Phase 1, so the `baseline_commit` recorded in `initiatives/current/config.yaml` is no longer reachable from HEAD | Inspect `git log` to see what happened. If the rewrite was intentional and the new history still contains every milestone commit, update `baseline_commit` in `config.yaml` to a fresh pre-initiative SHA, commit that change, retry. If the rewrite dropped commits, restore from reflog (`git reflog`) first |
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
