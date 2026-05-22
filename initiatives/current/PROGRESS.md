# observable-thresholds progress log

Cumulative milestone log for the `observable-thresholds` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[obs-thr/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

<!-- Block shape for each milestone (see automation/templates/progress_entry.md):

## M{N} — done YYYY-MM-DD

- **commit**: `<sha>` `[obs-thr/M{N}] <subject>`
- **tests**: <before> → <after> (+<delta>)
- **mypy**: clean | **ruff**: clean
- **files changed**: `<file1>`, `<file2>`, ...
- **exit gate**: `<quote from §2 of the milestone prompt>` → PASS (<one-line evidence>)
- **notes**: <optional, ≤1 line. Anything longer goes in HANDOFF.md.>
-->
