# ctx-mgmt-demo progress log

Cumulative milestone log for the `ctx-mgmt-demo` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[ctx-demo/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

## M1 — done 2026-05-25

- commit: [ctx-demo/M1] (see git log)
- tests: 816 -> 819 (+3)
- mypy: clean | ruff: clean
- files changed: `compact.py`, `cli.py`, `openai_cli.py`, `test_compact.py`, `test_cli.py`, `test_openai_cli_repl.py`
- exit gate: `simple-agent --help` AND `simple-agent-openai --help` both list `--microcompact-minutes`. `simple-agent-openai --help` additionally lists `--max-turns`. `pytest -q` is green with at least 3 new test cases covering the flags. -> PASS (819 passed, flags verified in both CLIs)
- notes: guard relaxed to threshold_minutes < 0 (accepts 0); M2 scenario 03 can use --microcompact-minutes 0 as originally planned.
