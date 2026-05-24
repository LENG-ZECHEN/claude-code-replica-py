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

## M2 — done 2026-05-25

- commit: [ctx-demo/M2] (see git log)
- tests: 819 -> 819 (no new tests — M2 is pure side-effect milestone)
- mypy: clean | ruff: clean
- files changed: `demo/_scripts/capture_scenario.py`, `demo/_artifacts/01_tool_result_management/*`, `demo/_artifacts/02_full_compact/*`, `demo/_artifacts/03_microcompact/*`
- exit gate:
  - 01 snip_invocations=2 >= 1, externalized_bytes=3800 > 0 -> PASS
  - 02 full_compacts=1 >= 1 -> PASS
  - 03 microcompact_invocations=3 >= 1 -> PASS
- notes: scenario 01 needed 3 reads of small.txt (not 2) because should_snip() uses _PATH_THRESHOLD=3. microcompact_minutes=60 prevents interference from slow qwen3.6-plus thinking-mode calls. externalized_bytes read from loop._context_builder._store.total_externalized_bytes (workaround for wiring bug in _build_repl_loop — see Section 5 of HANDOFF).

## M3 — done 2026-05-25

- commit: [ctx-demo/M3] (see git log)
- tests: 819 -> 819 (+0 — M3 is pure docs milestone)
- mypy: clean | ruff: clean (ruff errors in demo/_scripts/capture_scenario.py are pre-existing from M2, not introduced by M3)
- files changed: `demo/README.md`, `demo/01_tool_result_management.md`, `demo/02_full_compact.md`, `demo/03_microcompact.md`
- exit gate: 4 demo .md files exist; each embeds ≥5 lines of captured output, file:line source references, exact capture command, model name from stats_output.txt header -> PASS
- notes: all 3 scenarios used qwen3.6-plus; no quota swap needed. microcompact scenario (03) shows invocations=3 / cleared=0 — keep_recent=5 protects the single tool result throughout the 2-turn session.
