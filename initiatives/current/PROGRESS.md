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

## M2 — done 2026-05-23

- commit: `30945de` [obs-thr-hd/M2] fix preset bug + 8-field precedence matrix + MicroCompactor guard test
- tests: 584 -> 605 (+21)
- mypy: clean | ruff: clean
- files changed: `src/simple_coding_agent/cli.py`,
  `src/simple_coding_agent/openai_cli.py`, `tests/test_repl.py`,
  `tests/test_openai_cli_repl.py`, `tests/test_compact.py`
- exit gate: pytest green total >= 577 + test_repl.py 8-field x 3-state precedence matrix + MicroCompactor(0) raises ValueError + openai_cli sentinel symmetry -> PASS (605 passed; matrix 18, guard 1, symmetry 2; mypy+ruff clean)
- notes: bug fixed in shared `_build_repl_loop` via `_resolve_threshold` (explicit>preset>default); argparse defaults for the 3 int flags now `None`. MicroCompactor guard already existed (compact.py:303) so compact.py needed no src change — only the negative test was added. regression scan: no test relied on old argparse defaults (non-aggressive default preserved).
