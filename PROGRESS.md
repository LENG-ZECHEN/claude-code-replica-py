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

## M3 — done 2026-05-21

Phase C3 + C4 + B3. New `src/simple_coding_agent/metrics.py` ships
`MetricsCollector` with counters for full_compacts, snip_invocations,
microcompact_invocations, reactive_compacts, externalized_bytes, and
tokens_per_turn. `AgentLoop` accepts an optional `metrics=` kwarg,
bumps each counter at its fire site, samples
`ToolResultStore.total_externalized_bytes` (new read-only property)
after each turn, and exposes the collector via `LoopResult.metrics`.
`cli.py` wires the collector into REPL-spawned loops and adds a
`/stats` slash command (with help listing) that prints
`MetricsCollector.format_stats()`. `SessionMemory.dump_json` /
`load_json` provide atomic JSON persistence (tempfile + os.replace),
warn-and-continue on corrupted reads, and forward-compat extra-field
tolerance; the REPL auto-loads `<workspace>/.simple-agent/
session_memory.json` on start and auto-saves on /exit or EOF. New
tests: `tests/test_metrics_collector.py` (8), `tests/
test_session_memory_persist.py` (9), `tests/test_repl.py` (+2 stats
cases). pytest 436 → 455 (+19). M4 should pick up Phase D1 + D2 + D3
(Transcript.dump_json/load_json, cross-process session save/load,
`--resume <name>`) per RUNTIME_ACTIVATION_PLAN.md section 4.

## M4 — done 2026-05-21

Phase D1 + D2 + D3. `Transcript` gains `to_jsonable` /
`from_jsonable` / `dump_json` / `load_json` (drops `is_virtual`
messages by default; required-field validation raises `ValueError`).
New `src/simple_coding_agent/session_store.py` wraps a Transcript +
last `CompactSummary` into a `<sessions_dir>/<name>.json` file with
atomic write (`tempfile` + `os.replace` shared with Transcript via a
new `_atomic_write_json` helper). REPL gains `/save <name>` and
`/load <name>` slash commands plus a top-level `--resume <name>`
flag; missing-file and corrupted-JSON paths surface as exit code 2
with a clear message. `SIMPLE_AGENT_SESSIONS_DIR` env var overrides
the default `~/.simple-agent/sessions/`. New tests:
`tests/test_transcript_persist.py` (6), `tests/test_repl_save_load.py`
(8), `tests/test_resume_session.py` (4), `tests/
test_end_to_end_long_session.py` (2 scenarios from plan 3.5). pytest
455 → 475 (+20, meeting the M4 target). M5 should pick up Phase A2
+ B4 (openai_cli REPL + auto-learn cues) per RUNTIME_ACTIVATION_PLAN.md
section 4.

## M5 — done 2026-05-21

Phase A2 + B4 + plan 3.5 scenario 3. New
`src/simple_coding_agent/auto_learn.py` ships a pure-function
`detect_cue(text)` that returns the canonical cue label for "记住" /
"以后" / "don't" (apostrophe variants) / "prefer" (morphological
siblings), and a `format_hint(cue)` renderer. `cli.py` extracts
`_drive_repl_session` from `_run_repl` so `openai_cli` can share the
read-input/run-turn/slash-command/EOF/KeyboardInterrupt machinery
without duplication; it now wires a `ProjectMemory` (env-overridable
via `SIMPLE_AGENT_MEMORY_DIR`, default
`<workspace>/.simple-agent/memory/`) into every REPL loop and adds a
`/remember <type> <id> <body...>` slash command that uses
ProjectMemory's existing secret-rejection + path-traversal guards.
The REPL turn loop scans user input with `detect_cue` and prints
`format_hint` before invoking the loop. `openai_cli.py` gains
`--repl`, `--max-steps`, `--max-context-tokens`,
`--reserved-output-tokens`, `--resume` flags and a `_run_openai_repl`
that builds an `OpenAIProvider`-backed AgentLoop and delegates to
`cli._drive_repl_session`. New tests: `tests/test_auto_learn.py` (6),
`tests/test_repl_slash_remember.py` (8), `tests/test_openai_cli_repl.py`
(7), `tests/test_end_to_end_long_session.py` (+1 scenario 3). pytest
475 → 497 (+22, exceeding the M5 ≥485 target). M5 is the final
RUNTIME_ACTIVATION_PLAN milestone; the initiative is complete.
