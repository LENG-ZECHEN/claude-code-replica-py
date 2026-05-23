<!--
SKELETON for initiatives/current/prompts/M{N}.md
Phase 1 (RUNBOOK Step 8) fills in every {{placeholder}} below using:
  - YAML front-matter from initiatives/current/PLAN.md
  - Section bodies of PLAN.md
  - The milestone-specific `notes` field in the YAML
  - The current baseline from HANDOFF.md Section 3
  - CLAUDE.md execution rules
Sections §1-§5 are MANDATORY. Do not drop any.
§2.5 ("Out of scope") is REQUIRED — the milestone fails open if missing.
Comment blocks (HTML comments) are guidance to the bootstrap agent and
should NOT appear in the generated prompt.
-->

# {{INITIATIVE_SLUG}} — {{MILESTONE_ID}}: {{MILESTONE_NAME}}

You are an autonomous agent executing milestone **{{MILESTONE_ID}}** of the
**{{INITIATIVE_SLUG}}** initiative. This session was launched by
`automation/scripts/run_all_milestones.sh`. There is no user available to
ask — every decision must be made and documented now.

When you are done, the shell loop will start the next milestone if (and
only if) you have honored the exit ritual in §5 below.

## §1 Baseline (verify before any code change)

<!-- Phase 1 reads these from HANDOFF.md Section 3 ("Current repo state" = the baseline) at write-time -->
- Last commit: `{{BASELINE_COMMIT}}`
- pytest: {{BASELINE_PYTEST}} passing
- mypy: {{BASELINE_MYPY}}
- ruff: {{BASELINE_RUFF}}

Verify with:

```
git -C python-replica log --oneline -3
cd python-replica && pytest --tb=no -q
cd python-replica && mypy src/
cd python-replica && ruff check .
```

If the numbers do not match, **stop and report**. Do not start work
against a different baseline.

## §2 Scope (what THIS milestone implements)

<!-- Phase 1 copies these from PLAN.md / config.yaml -->
- **Phase IDs**: {{PHASE_IDS}}
- **Exit gate (must be objectively verifiable)**: {{EXIT_GATE}}
- **Expected files to touch**: {{EXPECTED_FILES}}

{{MILESTONE_NOTES}}

Scope is **tight**. Doing more than this is failure. §2.5 below lists
what you must NOT do even if it seems natural.

## §2.5 Out of scope (do NOT do these, even if tempting)

- **Do not implement any other milestone** in this initiative. Even if
  you "have time" or "see the obvious next step", stop at
  `{{MILESTONE_ID}}`.
- **Do not refactor unrelated modules.** Touch only files in the
  Expected-files list (§2), plus tests for those files.
- **Do not modify** `automation/scripts/run_all_milestones.sh`,
  `automation/RUNBOOK.md`, or `automation/templates/*.md` — those are
  the harness, not the project.
- **Do not modify** `CLAUDE.md` per-file summaries or `README.md` unless
  this milestone explicitly adds a new public symbol/CLI flag. The
  review session at the end of the initiative handles project-doc
  updates (per RUNBOOK Doc-update tiers); doing it here causes merge
  conflicts and wastes the review's audit.
- **Do not change public API signatures** of existing modules unless §2
  requires it.
- **Do not introduce new dependencies** in `pyproject.toml` unless §2
  requires it.

If you find an obvious bug or improvement outside scope, **write it in
your HANDOFF.md Section 5 ("risks" or as a deferred item) and move on**.
Do not fix it.

## §3 Mandatory reading (in order, before any code change)

1. **`python-replica/CLAUDE.md`** — architecture, per-file summaries,
   project-wide execution rules (TDD, immutability, file-size limits).
2. **`python-replica/initiatives/current/PLAN.md`** — this initiative's
   full brief, including the milestone tables.
3. **`python-replica/initiatives/current/config.yaml`** — machine-readable
   milestone table; confirms `exit_gate` + `phase_ids` for
   `{{MILESTONE_ID}}`.
4. **`python-replica/initiatives/current/HANDOFF.md`** — current state.
   Section 2 "Completed milestones" tells you what shipped already.
   Section 4 "Important constraints" lists invariants you MUST respect.
   Section 5 "Next milestone guidance" is written FOR you.
5. **`python-replica/initiatives/current/PROGRESS.md`** — terse fact log
   of each completed milestone (commit, test delta, files touched).
6. **The Expected-files list from §2** — read the source files this
   milestone will touch, plus their existing tests, before writing any
   code.
7. **If `{{MILESTONE_ID}}` is not M1**: run `git -C python-replica log
   --oneline -10` and `git -C python-replica show HEAD~1` to see what
   the immediately prior milestone changed. (`HEAD~1` is the prior
   milestone's commit because each milestone commits exactly once
   before the loop advances; if you suspect that invariant has been
   violated, use `git -C python-replica log {{BASELINE_COMMIT}}..HEAD
   --oneline | grep -F "[{{COMMIT_PREFIX}}/" | head -1` instead and
   `git -C python-replica show <sha>` to inspect that SHA. The `-C
   python-replica` is required because the autonomous loop launches
   `claude --print` from `/Users/leng/my-cc-py`, not from inside the
   repo. The `grep -F` is required because the literal `[` in the
   marker would otherwise be parsed as an unclosed character class
   (e.g. `[mcp-int/` triggers `grep: invalid character range`); `-F`
   forces fixed-string matching. The `{{BASELINE_COMMIT}}..HEAD` range
   matches what `run_all_milestones.sh` uses, so the fallback stays
   consistent with the resumability check and is robust against any
   prefix-collision edge case Phase 1 pre-flight may have missed.)
8. **If `{{MILESTONE_ID}}` > M2**: skim
   `initiatives/current/logs/M{N-1}.log` for any anomalies (warnings,
   retries, KeyboardInterrupts) that didn't make it into HANDOFF
   Section 2 design-decisions.

**Before invoking any Edit or Write tool**, print a **5-bullet summary**
to stdout (plain text, not a tool call, not a TaskCreate todo, not a
file write) of what you learned from PLAN / HANDOFF / PROGRESS / the
previous commit. If those sources disagree on a fact, treat HANDOFF as
advisory and `git diff` + test output as source of truth. This summary
lives only in the captured session log under `initiatives/current/logs/`
(not in any committed file) — its purpose is to force genuine reading
rather than skimming. If you cannot produce a substantive 5-bullet
summary, you have not read enough; go back to §3.

## §4 Implementation requirements

Follow execution rules documented in `python-replica/CLAUDE.md`. In
particular:

- **TDD**: write tests first (RED — must actually run and fail before
  implementation), implement (GREEN), refactor. Every new code path
  needs a test before the implementation lands.
- **Immutability**: dataclasses prefer `frozen=True` where appropriate;
  never mutate inputs; return new objects.
- **File limits**: functions ≤50 lines, files ≤800 lines.
- **Determinism in tests**: `MockProvider`, `tmp_path`, `monkeypatch`.
  No network. No real API key.
- **No swallowed exceptions**.
- **No `git add -A`** — stage explicit paths only.
- **Match style** of existing modules (see CLAUDE.md per-file summaries).

After every meaningful diff, run:

```
cd python-replica && pytest --tb=no -q
cd python-replica && mypy src/
cd python-replica && ruff check .
```

All three must be green before you commit.

## §5 Exit ritual (MANDATORY)

After your milestone work passes the exit gate in §2, before stopping,
perform these steps **in order**. The shell script independently
verifies the **5 side-effects** listed at the end of this section.
Step 1 below ("Confirm exit gate met") is **honor-system** — the script
cannot inspect whether you actually quoted the right command output, so
the 5 mechanical checks are produced by steps 2-4 (commit, PROGRESS
append, HANDOFF rewrite) plus the standing pytest-green requirement
from §4. Skipping step 1 makes a green run meaningless even though it
would still pass the gate; do not skip it.

### 1. Confirm exit gate met (objectively)

Quote the concrete check from §2 verbatim and show the command output
that proves it. Example:

```
$ pytest tests/test_mcp_handshake.py --tb=no -q
........  8 passed in 0.4s

$ python -m simple_coding_agent.cli --repl < /tmp/probe-input
(cue detected: '记住' -- type /remember ...)
```

"Implementation feels complete" is NOT acceptable. The gate must be
objectively verified by a command's output.

### 2. Commit with explicit paths

Never `git add -A`. The commit subject MUST start with
`[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}]`:

```
git -C python-replica add <list each modified/new file>
git -C python-replica commit -m "[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}] <one-line summary>"
```

The shell loop's first exit-gate check is `git log -1 | grep -qF
"[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}]"`. Without this commit the
loop halts and subsequent milestones will NOT run.

**Do NOT `git commit --amend` to embed this commit's own SHA into
PROGRESS.md / HANDOFF.md.** Reading `git rev-parse HEAD` before
amending captures the pre-amend SHA, which becomes unreachable after
the amend rewrites the commit (`git merge-base --is-ancestor` will
return false for the recorded SHA). The garbage collector will
eventually delete that object, breaking `git show <sha>`
traceability. If you need the SHA in PROGRESS.md / HANDOFF.md,
choose one of:

- **Omit the SHA** entirely from the body — cite "HEAD at commit
  time" and rely on `[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}]` to locate
  the commit; or
- **Add a second** `[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}]` commit
  that fills in the first commit's SHA. See `obs-thr-harden` M3 →
  `4582997` ("fill M3 commit SHA (9b00767) into roadmap + handoff +
  progress") for the canonical two-commit pattern.

The shell loop's exit-gate check counts ALL `[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}]`
commits in `baseline_commit..HEAD`, so a follow-up SHA-fill commit
does not interfere.

### 3. Append a block to `initiatives/current/PROGRESS.md`

Use the terse format in `automation/templates/progress_entry.md`. One
block per milestone. PROGRESS.md is the **fact log for the final
review** — narrative belongs in HANDOFF, not here.

Block shape:

```
## {{MILESTONE_ID}} — done YYYY-MM-DD

- commit: <sha> [{{COMMIT_PREFIX}}/{{MILESTONE_ID}}] <subject>
- tests: <before> -> <after> (+N)
- mypy: clean | ruff: clean
- files changed: `<file1>`, `<file2>`, ...
- exit gate: <quote from §2> -> PASS (<one-line evidence>)
- notes: <optional, ≤1 line>
```

### 4. Rewrite `initiatives/current/HANDOFF.md`

Use the 5-section structure in `automation/templates/handoff_milestone.md`.
The structure is non-negotiable.

**Section 2 "Completed milestones"**: APPEND your own subsection for
`{{MILESTONE_ID}}`. Do NOT delete or rewrite prior milestone blocks —
each milestone is the source of truth on itself.

**Section 4 "Important constraints"**: if your work froze any file,
behavior, or interface that subsequent milestones must not change, add
it here. This is how invariants propagate across the initiative.

**Section 5 "Next milestone guidance"**: write as if onboarding the
next agent in person. Include:
- next scope (paraphrase from PLAN + anything you learned in
  `{{MILESTONE_ID}}` that sharpens it)
- relevant files (which src + test files the next milestone will likely
  touch)
- expected tests (which test files to extend)
- risks (surprises you ran into that the next milestone should watch
  for)

{{IF_LAST_MILESTONE_BLOCK}}

---

Do not skip any step. After your commit, the shell script independently
verifies:

1. The commit subject contains `[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}]`.
2. `initiatives/current/HANDOFF.md` was modified in your commit.
3. `initiatives/current/PROGRESS.md` contains a heading matching the
   regex `^## {{MILESTONE_ID}} — done YYYY-MM-DD` (anchored — a stray
   `{{MILESTONE_ID}}` substring in a notes line does NOT satisfy this).
4. `pytest --tb=no -q` is still green.
5. `initiatives/current/HANDOFF.md` contains the required 5-section
   structure (verbatim headers: `## 1. Current initiative`, `## 2.
   Completed milestones`, `## 3. Current repo state`, `## 4. Important
   constraints`, `## 5. Next milestone guidance`). A free-form HANDOFF
   fails this check even if the file was modified.
6. **Append-only contract.** For every prior milestone `M{i}` your
   initiative has already shipped (every `[{{COMMIT_PREFIX}}/M{i}]`
   commit in `baseline_commit..HEAD`):
   - `initiatives/current/PROGRESS.md` still contains the
     `^## M{i} — done YYYY-MM-DD` block from that milestone;
   - `initiatives/current/HANDOFF.md` still contains the
     `^### M{i}$` subsection under "## 2. Completed milestones".
   Rewriting either file from scratch and only including your own
   `M{{MILESTONE_ID}}` block is a HARD FAILURE here — prior milestones
   are the source of truth on themselves; you APPEND only.

Any of those six failing halts the loop. The final review session will
also audit whether you stayed in scope and whether your HANDOFF accurately
describes your diff.
