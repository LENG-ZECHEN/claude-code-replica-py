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

## M1 — done 2026-05-22

- **commit**: `a052056` `[obs-thr/M1] wire Tracer Protocol + --verbose flag across context/memory pipeline`
- **tests**: 520 → 542 (+22)
- **mypy**: clean | **ruff**: clean
- **files changed**: `src/simple_coding_agent/trace.py` (new), `src/simple_coding_agent/{auto_learn,claude_md,cli,compact,context,loop,memory,openai_cli,snip,tool_result_store}.py`, `examples/microcompact_demo.py`, `tests/test_trace.py` (new), `tests/test_{cli,loop,microcompact_runtime,openai_cli_repl,repl}.py`
- **exit gate**: `simple-agent --repl --verbose` stderr emits `[trace] [budget]` + `[trace] [memory_select]`; without `--verbose` stderr silent; pytest ≥ 540; mypy + ruff clean → **PASS** (smoke run captured `[trace] [budget|claude_md|memory_select|microcompact]` on stderr; baseline run produced 0 lines; pytest 542, mypy 21 files clean, ruff clean)
- **notes**: agent session terminated by Claude Code thrash-loop protection at turn 243 before reaching §5 exit ritual; source work was complete (last tool_result success at transcript line 1727). This commit is the manual exit-ritual collation per RUNBOOK recovery path.

## M2 — done 2026-05-23

- **commit**: `14299af` `[obs-thr/M2] add --aggressive-thresholds preset + SnipTool/MicroCompactor constructor params`
- **tests**: 542 → 551 (+9)
- **mypy**: clean | **ruff**: clean
- **files changed**: `src/simple_coding_agent/cli.py`, `src/simple_coding_agent/compact.py`, `src/simple_coding_agent/openai_cli.py`, `src/simple_coding_agent/snip.py`, `examples/aggressive_thresholds_demo.py` (new), `tests/test_snip.py`, `tests/test_repl.py`, `tests/test_openai_cli_repl.py`, `tests/test_aggressive_thresholds_demo.py` (new)
- **exit gate**: `--aggressive-thresholds` REPL startup banner starts with `[aggressive-thresholds]`; demo shows full_compacts=1, snip_runs=6; pytest ≥ 545; mypy + ruff clean → **PASS** (smoke: banner verified; demo: full_compacts=1, snip_runs=6; pytest 551, mypy 21 files clean, ruff clean)
- **notes**: agent session terminated by API usage exhaustion before reaching §5 exit ritual; source work was complete. This commit is the manual exit-ritual collation per RUNBOOK recovery path.
