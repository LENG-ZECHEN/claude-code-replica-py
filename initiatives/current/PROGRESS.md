# ctx-mgmt-pdf-align progress log

Cumulative milestone log for the `ctx-mgmt-pdf-align` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[ctx-pdf/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

<!-- No milestone blocks yet. The first real milestone (M1) appends its
     own block at exit ritual step 3, using the shape:

## M{N} — done YYYY-MM-DD

- **commit**: `<sha>` `[ctx-pdf/M{N}] <subject>`
- **tests**: <prev> → <new> (+<delta>)
- **mypy**: <status> | **ruff**: <status>
- **files changed**: `<file1>`, `<file2>`, ...
- **exit gate**: `<gate text from §2 of the milestone prompt>` → PASS (<one-line evidence>)
- **notes**: <optional, ≤1 line. Anything longer goes in HANDOFF.md.>
-->
