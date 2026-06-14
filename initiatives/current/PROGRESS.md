# session-memory-dream progress log

Cumulative milestone log for the `session-memory-dream` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[sm-dream/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

Each milestone agent APPENDS one block at exit ritual, formatted:

```
## M{N} — done YYYY-MM-DD

- **commit**: `(see git log)` `[sm-dream/M{N}] <subject>`
- **tests**: <before> → <after> (+N)
- **mypy**: clean | **ruff**: clean
- **files changed**: `<file1>`, `<file2>`, ...
- **exit gate**: `<gate text from §2>` → PASS (<one-line evidence>)
- **notes**: <optional, ≤1 line>
```

<!-- Milestone blocks begin below. The first real milestone (M1) appends
     its block here; do not place any entry above this line. -->
