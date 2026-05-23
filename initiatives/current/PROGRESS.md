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

## M1 — done 2026-05-23

- commit: `71d3c80` `[obs-thr-hd/M1] harden StderrTracer + expand leak/roundtrip coverage`
- tests: 557 -> 584 (+27)
- mypy: clean | ruff: clean
- files changed: `src/simple_coding_agent/trace.py`, `tests/test_trace.py`
- exit gate: pytest green total >= 565 + test_trace.py gains 4-shape secret-leak parametrize, closed-stream guard test, reactive e2e, whitespace/non-string demo-parser roundtrip -> PASS (584 passed; named tests green; mypy+ruff clean)
- notes: closed-stream guard catches only (OSError, ValueError); `_render_value` repr-quotes whitespace/non-scalar values.
