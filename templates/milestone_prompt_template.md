I'm continuing work on simple_coding_agent, a Python replica of Claude Code
v2.1.88's context-management and memory pipeline.

This is an autonomous milestone-runner session. The shell loop in
python-replica/scripts/run_all_milestones.sh launched me. After this
session ends, the loop will start the next milestone. I have NO user to
ask — every decision must be made and documented now.

== Workspace context ==
Your cwd is /Users/leng/my-cc-py. The directory layout:
  python-replica/          ← THE PROJECT (Python replica codebase)
  claude-code-source-code/ ← TypeScript reference (READ-ONLY, do not modify)
  docs/                    ← high-level specs

== Before doing anything ==
1. Read python-replica/CLAUDE.md (full architecture + completed P-roadmap +
   Active Initiative section with Resumption Protocol + Exit Ritual).
2. Read python-replica/RUNTIME_ACTIVATION_PLAN.md
     - Section 4 for milestone {{MILESTONE}}'s scope and exit gate
     - Section 5 for execution rules (TDD, immutability, file limits)
3. Read python-replica/HANDOFF.md if it exists — Section 3 ("Decisions
   Made That Diverge From Plan") is MANDATORY reading.
4. Confirm baseline:
     git -C python-replica log --oneline -10
     cd python-replica && pytest --tb=no -q
   Then return to /Users/leng/my-cc-py for further work.

== Execute Milestone {{MILESTONE}} only ==
  - Phase IDs: {{PHASE_IDS}}
  - Test plan: RUNTIME_ACTIVATION_PLAN.md sections {{SECTION_IDS}}

All file paths in instructions below are relative to /Users/leng/my-cc-py
unless otherwise stated. The project lives under python-replica/; do not
create new directories outside python-replica/ for this work.

Out of scope: any other milestone. Do NOT touch out-of-milestone code.
Do NOT modify claude-code-source-code/ (it is reference only).

== Permission environment ==
This session runs under a curated allowedTools whitelist:
  - File ops: Read, Write, Edit, Glob, Grep
  - Task ops: TaskCreate / TaskUpdate / TaskList / TaskGet / TaskOutput
  - Bash:     git, pytest, python, mypy, ruff, pip, ls, cat, head, tail,
              grep, find, wc, diff, mkdir, chmod, touch, echo, printf
  - Denied:   rm, curl, wget, sudo, ssh, git push --force

If you need a tool outside this set: STOP, write a clear blocker note to
python-replica/HANDOFF.md Section 4, then exit. The loop will halt at the
missing P9-{{MILESTONE}} commit gate, which is the intended fail-safe.

== Exit ritual (MANDATORY) ==
The loop's exit-gate check is:
  git -C python-replica log --oneline -1 | grep "P9-{{MILESTONE}}"
Without this commit, the loop stops and M{{MILESTONE}}+1 onwards will NOT
run. Follow these 4 steps exactly:

1. Confirm Milestone {{MILESTONE}}'s exit gate (per plan Section 4) is met.

2. Commit with explicit paths (never `git add -A`):
     cd python-replica
     git add <list each modified/new file>
     git commit -m "P9-{{MILESTONE}}: <one-line summary>"

3. Append a "P9 — M{{MILESTONE}} complete" entry to python-replica/CLAUDE.md
   mirroring the existing P1-P9 format, directly below the existing
   P9-M{prev} entry.

4. Append a one-line summary to python-replica/PROGRESS.md (create the
   file if it does not exist).

5. Overwrite python-replica/HANDOFF.md using
   python-replica/templates/handoff_template.md, with all placeholders
   filled, to hand off to the next milestone session. Section 3
   (decisions that diverge) is the most important — the next session
   reads it first.

Confirm understanding by reading python-replica/CLAUDE.md,
python-replica/RUNTIME_ACTIVATION_PLAN.md, and python-replica/HANDOFF.md
above. Then proceed directly to TDD implementation. There is no approval
gate; this is autonomous.
