# RUNTIME_ACTIVATION_PLAN progress log

Cumulative milestone log for the P9 initiative. Append one block per
milestone, newest at the bottom.

## M1 — done 2026-05-21

Phase A1 + A3 + A4 + B1. cli.py adds `--repl`, `--max-steps`,
`--max-context-tokens`, `--reserved-output-tokens`, and a `--stream`
extension. New memory_cli.py exposes `simple-agent memory {add,list,
delete,search,show}` over `ProjectMemory`. pytest 392 → 421 (+29).
Commit `4cdbc79`. M2 should pick up Phase C1 + C2 (stress + microcompact
demos) with the section 3.3 tests.

## M2 — done 2026-05-21

Phase C1 + C2. examples/stress_demo.py drives full-compact (210k-char
transcript inside a 10k-token budget) and reactive-compact
(PromptTooLongError → retry) end-to-end. examples/microcompact_demo.py
seeds 120-min-aged timestamps so MicroCompactor's cold-cache cleanup
fires inside AgentLoop. Both demos print the normative exit-gate markers
`compact fired (messages_summarized=N)` and `microcompact fired (results
cleared=N)`. Section 3.3 tests (`test_stress_full_compact.py` +
`test_microcompact_runtime.py`) plus new demo-stdout tests
(`test_stress_demo.py` + `test_microcompact_demo.py`) land together.
pytest 421 → 436 (+15). `.gitignore` adds `logs/` to keep autonomous-loop
artifacts out of `git status`. M3 should pick up Phase C3 + C4 + B3
(MetricsCollector, REPL `/stats`, SessionMemory persistence) per
RUNTIME_ACTIVATION_PLAN.md section 4.
