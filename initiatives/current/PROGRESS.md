# obs-thr-harden progress log

Cumulative milestone log for the `obs-thr-harden` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[obs-thr-hd/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

<!-- No milestone blocks yet — M1 appends the first one at its exit ritual.

Block shape (per automation/templates/progress_entry.md):

## M{N} — done YYYY-MM-DD

- commit: <sha> [obs-thr-hd/M{N}] <subject>
- tests: <before> -> <after> (+N)
- mypy: clean | ruff: clean
- files changed: `<file1>`, `<file2>`, ...
- exit gate: <quote from §2 of the milestone prompt> -> PASS (<one-line evidence>)
- notes: <optional, ≤1 line>
-->
