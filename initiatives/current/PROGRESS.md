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
