<!--
SKELETON for initiatives/current/prompts/M{N}.md
Phase 1 (RUNBOOK Step 8) fills in every {{placeholder}} below using:
  - YAML front-matter from initiatives/current/PLAN.md
  - Section bodies of PLAN.md
  - The milestone-specific `notes` field in the YAML
  - The current baseline from HANDOFF.md Section 1
  - CLAUDE.md execution rules
Sections §1-§5 are MANDATORY. Do not drop any.
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

<!-- Phase 1 reads these from HANDOFF.md Section 1 at write-time -->
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

## §2 Scope

<!-- Phase 1 copies these from PLAN.md / config.yaml -->
- **Phase IDs**: {{PHASE_IDS}}
- **Exit gate**: {{EXIT_GATE}}

{{MILESTONE_NOTES}}

<!-- end of milestone-specific scope -->

Out of scope: every other milestone. Do NOT touch out-of-milestone code
even if it looks improvable.

## §3 Mandatory reading

Before writing any code:

1. **`python-replica/CLAUDE.md`** — architecture, per-file summaries,
   project-wide execution rules.
2. **`python-replica/initiatives/current/PLAN.md`** — this initiative's
   full brief (you are working on {{MILESTONE_ID}} of it).
3. **`python-replica/initiatives/current/HANDOFF.md`** — Section 3
   "Decisions That Diverge From Plan" is **mandatory** reading; previous
   milestones may have made choices that affect yours.
4. **`python-replica/initiatives/current/PROGRESS.md`** — quick scan of
   what previous milestones produced (counts, files touched).

## §4 Implementation requirements

Follow the execution rules documented in `python-replica/CLAUDE.md`. In
particular:

- **TDD**: write tests first (RED), implement (GREEN), refactor. Every
  new code path needs a test before the implementation lands.
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

## §5 Exit ritual (MANDATORY — the script's exit-gate check depends on this)

After your milestone work passes the exit gate in §2, before stopping,
perform these steps **in order**:

1. **Confirm exit gate met.** Quote the concrete check from §2 and show
   the command output that proves it.

2. **Commit with explicit paths** (never `git add -A`). The commit
   subject MUST start with `[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}]`:

   ```
   git -C python-replica add <list each modified/new file>
   git -C python-replica commit -m "[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}] <one-line summary>"
   ```

   The shell loop's exit-gate check is `git log -1 | grep -q
   "\[{{COMMIT_PREFIX}}/{{MILESTONE_ID}}\]"`. Without this commit the
   loop halts and subsequent milestones will NOT run.

3. **Append a block to `initiatives/current/PROGRESS.md`**. Format
   exactly like `automation/templates/progress_entry.md` (one block per
   milestone). Include: pytest count delta, mypy/ruff status, files
   changed (one line each), what {{NEXT_MILESTONE_ID}} should pick up.

4. **Rewrite `initiatives/current/HANDOFF.md` for {{NEXT_MILESTONE_ID}}**.
   Use `automation/templates/handoff_milestone.md`. Section 3 "Decisions
   That Diverge From Plan" is the most important — the next session
   reads it first. Be specific about renames, deferred work, alternative
   library choices, and anything that surprised you.

{{IF_LAST_MILESTONE_BLOCK}}

Do not skip any step. The exit ritual is what makes the autonomous loop
work; the review session after the last milestone will audit whether you
honored it.
