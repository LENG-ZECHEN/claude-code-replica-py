# RUNTIME_ACTIVATION_PLAN

> **STATUS: complete** — 2026-05-21. Final commit: `de3ecad`.
> pytest 392 → 497 (+105 over 5 milestones). mypy + ruff clean.
> Archived from project root to `initiatives/_archive/` on 2026-05-22.
> See `HANDOFF.md` for terminal state and `PROGRESS.md` for per-milestone log.

> **Purpose**: All context-management and memory mechanisms in
> `simple_coding_agent` are implemented and unit-tested (392 passing as
> of this writing), but the current one-shot CLI never runs long enough
> to actually trigger them in practice. This document is the plan to
> add runtime entry points (REPL, memory CLI, stress demos, session
> persistence, metrics) so the shipped P1-P8 mechanisms become
> reachable, observable, and demonstrable in a real session.
>
> **Audience**: a fresh Claude Code session opened against
> `/Users/leng/my-cc-py/python-replica`, with no memory of the
> conversation that produced this plan.
>
> **Pre-reading (mandatory)**:
> 1. `CLAUDE.md` — architecture + completed P1-P8 roadmap
> 2. `README.md` — current entry points + safety guarantees
> 3. Skim `src/simple_coding_agent/loop.py`, `compact.py`, `memory.py`
>    to confirm component shape before writing tests.

---

## 1. Maturity Diagnostic

Four scoring layers per component:
- **Unit** — pure-function correctness (covered by existing tests)
- **Wired** — wired into `AgentLoop` properly
- **Runtime** — how often it actually fires in a real CLI run
- **Observ.** — can a user see that it fired

10 = production-ready, 0 = absent. Bold = the gap this plan fixes.

### 1.1 Context Management Subsystem

| Component                                     | Unit | Wired | Runtime | Observ. | Overall |
|-----------------------------------------------|------|-------|---------|---------|---------|
| `ContextBudget`                               | 10   | 10    | 10      | 6       | 9       |
| `ContextBuilder.build()` 5-step pipeline      | 9    | 10    | 10      | 7       | 9       |
| `ToolResultStore` (50k/200k caps + cache)     | 10   | 10    | **8**   | 5       | 8       |
| `SnipTool`                                    | 10   | 10    | **4**   | 5       | 7       |
| `ContextCompactor.should_compact + compact`   | 10   | 10    | **2**   | 6       | 7       |
| `MicroCompactor` (60-min cold cache)          | 10   | 10    | **0**   | 4       | 6       |
| `LLMSummarizer`                               | 9    | 10    | **0**   | 3       | 5       |
| Reactive Compact (PromptTooLong retry)        | 10   | 10    | **1**   | 4       | 6       |
| `_remove_orphan_tool_results`                 | 10   | 10    | 8       | 3       | 8       |

**Key findings:**
- All unit logic is production-grade; immutability + idempotency are
  verified by 392 tests.
- **Runtime reachability is the gap**: snip / microcompact /
  full-compact / reactive-compact almost never fire in one-shot CLI
  runs of <=10 turns.
- Observability is weak: `AgentStep.compacted` is a bool with no
  per-turn token counts, no per-mechanism counters, no
  externalized-bytes total.

### 1.2 Memory Subsystem

| Component                                  | Unit | Wired | Runtime | Observ. | Overall |
|--------------------------------------------|------|-------|---------|---------|---------|
| `MemoryEntry` / `MemoryType` (4 types)     | 10   | 10    | 7       | 8       | 9       |
| `SessionMemory` (in-process)               | 10   | 9     | **3**   | 6       | 7       |
| `ProjectMemory` (file-backed)              | 10   | 9     | **2**   | 5       | 6       |
| `MemorySelector` Jaccard top-5             | 8    | 10    | **2**   | 6       | 6       |
| Secret rejection + path-traversal guard    | 10   | 10    | 10      | 8       | 10      |
| `ClaudeMdLoader`                           | 10   | 10    | 10      | 6       | 9       |
| **Auto-write (learn from conversation)**   | **0**| **0** | 0       | —       | **0**   |
| Cross-session memory injection observable  | 10   | 10    | **1**   | 4       | 6       |

**Key findings:**
- Storage + selection layer is complete.
- **No write path from the CLI**: users cannot populate `ProjectMemory`
  without writing Python code, so the Jaccard selector has nothing to
  rank.
- **Auto-write (Claude Code's headline feature) is completely missing**.
- `ClaudeMdLoader` is the only memory component fully reachable today.

---

## 2. Phase Plan

### Phase A — Long-session entry points (REQUIRED)

| ID | Task | ~LoC | Unlocks |
|----|------|------|---------|
| A1 | Add `--repl` to `cli.py` (Mock provider, shared `AgentLoop`, slash commands `/exit` `/help`) | 40 | snip + full-compact + reactive-compact reachable |
| A2 | Same `--repl` for `openai_cli.py` (real provider) | 30 | reactive-compact reachable with real API |
| A3 | `--max-steps N` flag on both CLIs | 5 | snip threshold reachable on normal tasks |
| A4 | `--max-context-tokens` + `--reserved-output-tokens` flags | 10 | small-budget runs let full-compact fire deterministically |

### Phase B — Memory writability (REQUIRED)

| ID | Task | ~LoC | Unlocks |
|----|------|------|---------|
| B1 | New `memory_cli.py`: `simple-agent memory {add,list,delete,search,show}` | 120 | `ProjectMemory` CRUD + secret guard + path guard |
| B2 | REPL slash command `/remember <type> <name> <body>` | 30 | low-friction write during conversation |
| B3 | `SessionMemory.dump_json()` / `load_json()` + REPL auto-save/load | 50 | `SessionMemory` survives process exit |
| B4 (enhance) | Auto-learn hook: scan user input for "记住"/"以后"/"don't"/"prefer" cues, prompt to save | 80 | Approaches real Claude Code experience |

### Phase C — Reachability demos + metrics (ENHANCE)

| ID | Task | ~LoC | Unlocks |
|----|------|------|---------|
| C1 | `examples/stress_demo.py` — scripted 200k+ char conversation, prints compact events | 100 | full-compact + reactive-compact end-to-end visible |
| C2 | `examples/microcompact_demo.py` — backdated timestamps + monkeypatched `datetime`, fires microcompact | 60 | microcompact end-to-end visible |
| C3 | New `metrics.py` (`MetricsCollector`): counters for snip/micro/full/reactive/externalized bytes/token estimates per turn | 60 | full pipeline observable |
| C4 | `LoopResult.metrics` field + REPL `/stats` command | 20 | user-visible |

### Phase D — Cross-process session persistence (ENHANCE)

| ID | Task | ~LoC | Value |
|----|------|------|-------|
| D1 | `Transcript.dump_json(path)` / `Transcript.load_json(path)` | 40 | persistence primitive |
| D2 | REPL `/save <name>` `/load <name>` to `~/.simple-agent/sessions/<name>.json` | 50 | cross-process resume; `CompactSummary` survives |
| D3 | `simple-agent --resume <name>` and `--repl --resume <name>` | 10 | CLI-level resume |

---

## 3. Detailed Test Plan

All new tests follow project conventions:
- pytest, AAA structure
- `MockProvider` for determinism (no network)
- `tmp_path` fixture for filesystem tests
- Immutable assertions: never mutate inputs in fixtures
- `monkeypatch` for time / env / stdin

### 3.1 Phase A tests

**`tests/test_repl.py`** (NEW, ~15 cases):

| # | Case | Asserts |
|---|------|---------|
| 1 | `test_repl_carries_transcript_across_inputs` | After two inputs, `transcript.all_messages()` contains both user messages |
| 2 | `test_repl_exit_command_returns_zero` | `/exit` -> exit code 0 |
| 3 | `test_repl_quit_alias_works` | `/quit` is an alias for `/exit` |
| 4 | `test_repl_help_lists_commands` | `/help` stdout contains `/exit` `/help` and any custom commands |
| 5 | `test_repl_unknown_slash_command_prints_hint` | `/foo` prints "unknown command, try /help" |
| 6 | `test_repl_keyboardinterrupt_does_not_drop_transcript` | Ctrl-C during turn N preserves transcript for turn N+1 |
| 7 | `test_repl_empty_input_skipped` | Bare Enter does not call provider |
| 8 | `test_repl_with_max_steps_override` | `--max-steps 50` sets `loop._max_steps == 50` |
| 9 | `test_repl_passes_workspace_to_tools` | File ops outside workspace raise `WorkspaceBoundaryError` |
| 10 | `test_repl_long_conversation_triggers_compact` | 20 scripted turns with growing context -> `LoopResult.compacted is True` at least once |
| 11 | `test_repl_compact_summary_appears_in_next_system_prompt` | After compact, next turn's `ContextBuilder.build()` system contains `## Conversation Summary` |
| 12 | `test_repl_stdin_eof_exits_cleanly` | EOF on stdin = same as `/exit` |
| 13 | `test_repl_streams_text_when_stream_flag_set` | `--stream` route uses `run_stream` and yields `text_delta` events |
| 14 | `test_repl_max_context_tokens_flag_propagates` | `--max-context-tokens 5000` sets `ContextBudget.max_tokens == 5000` |
| 15 | `test_repl_reserved_output_tokens_flag_propagates` | `--reserved-output-tokens 1000` sets budget correctly |

**Adds to `tests/test_cli.py`**:
- `test_cli_repl_flag_dispatches_to_repl_handler`
- `test_cli_max_steps_flag_default_is_10`

### 3.2 Phase B tests

**`tests/test_memory_cli.py`** (NEW, ~12 cases):

| # | Case | Asserts |
|---|------|---------|
| 1 | `test_add_creates_entry_json_on_disk` | After `memory add user foo "body"`, `<dir>/<id>.json` exists with correct fields |
| 2 | `test_add_rejects_secret_body` | `"API_KEY=abc"` body -> exit 2, no file created |
| 3 | `test_add_rejects_path_traversal_id` | id `../../etc/passwd` -> exit 2 |
| 4 | `test_add_rejects_unknown_type` | `memory add foo name body` -> exit 2 with type-list hint |
| 5 | `test_list_prints_all_entries` | 3 entries on disk -> stdout has 3 lines |
| 6 | `test_list_type_filter` | `--type feedback` returns only feedback entries |
| 7 | `test_delete_removes_file_and_updates_manifest` | After delete, `<id>.json` gone, `MEMORY.md` line gone |
| 8 | `test_delete_missing_id_is_idempotent` | Deleting nonexistent id -> exit 0, no error |
| 9 | `test_search_substring_match` | Body containing "fastapi" -> matches `memory search fastapi` |
| 10 | `test_show_prints_full_body` | Body of any length printed in full |
| 11 | `test_storage_dir_from_env` | `SIMPLE_AGENT_MEMORY_DIR=/tmp/x` honored |
| 12 | `test_storage_dir_default_under_workspace` | Default storage is `<workspace>/.simple-agent/memory/` |

**`tests/test_session_memory_persist.py`** (NEW, ~6 cases):

| # | Case | Asserts |
|---|------|---------|
| 1 | `test_dump_load_roundtrip_preserves_entries` | Save -> load -> equal entries |
| 2 | `test_load_missing_file_returns_empty_store` | No file -> empty `SessionMemory`, no exception |
| 3 | `test_load_corrupted_json_returns_empty_with_warning` | Bad JSON -> empty store, `caplog.records` has warning |
| 4 | `test_dump_atomic_write_via_tempfile_rename` | Simulate write failure mid-dump -> original file intact |
| 5 | `test_dump_preserves_memory_type` | All 4 types round-trip correctly |
| 6 | `test_load_ignores_extra_fields_for_forward_compat` | Future fields in JSON do not break load |

**`tests/test_repl_slash_commands.py`** (NEW, ~5 cases for B2):
- `test_remember_command_adds_to_project_memory`
- `test_remember_command_rejects_unknown_type`
- `test_remember_command_rejects_secret_body`
- `test_remember_command_with_no_args_prints_usage`
- `test_remember_persists_across_repl_restarts` (depends on B3)

### 3.3 Phase C tests

**`tests/test_stress_full_compact.py`** (NEW):

```
test_full_compact_fires_after_large_tool_results:
  Arrange: ContextBudget(max_tokens=10_000, reserved=2_000),
           MockProvider scripted with 15 turns of 1000-char read_file
           outputs
  Act:     loop.run("...")
  Assert:  result.compacted is True
           result.last_summary.messages_summarized >= 5
           result.last_summary.pre_token_count >
             result.last_summary.post_token_count

test_reactive_compact_on_prompt_too_long:
  Arrange: MockProvider raises PromptTooLongError on turn 2 only
  Act:     loop.run(...)
  Assert:  result.compacted is True
           result.status == LoopStatus.COMPLETED  (retried once)

test_reactive_compact_twice_returns_max_tokens:
  Arrange: MockProvider raises PromptTooLongError on every call
  Act:     loop.run(...)
  Assert:  result.status == LoopStatus.MAX_TOKENS  (no third retry)

test_tool_result_externalization_total_cap:
  Arrange: 5 tool results x 60_000 chars (= 300k total)
  Act:     ContextBuilder.build()
  Assert:  Total inline content <= DEFAULT_TOTAL_BUDGET_CHARS (200_000)
           At least 1 result has persisted_path set
           Largest-first ordering: biggest results externalized first

test_snip_fires_when_same_path_read_three_times:
  Arrange: 3 read_file calls on same path within one run
  Act:     loop.run(...)
  Assert:  First 2 tool_results have content == SNIPPED_CONTENT
           Third (latest) tool_result preserved
```

**`tests/test_microcompact_runtime.py`** (NEW):

```
test_microcompact_fires_when_assistant_older_than_60min:
  Arrange: Build a transcript whose last assistant message has
           timestamp = now - 61 min; monkeypatch datetime.now in
           simple_coding_agent.compact module
  Act:     loop.run("new input")
  Assert:  Compactable tool results in pre-existing transcript
           have content == CLEARED_TOOL_RESULT_CONTENT
           Non-compactable tool results preserved unchanged

test_microcompact_runs_at_most_once_per_loop_instance:
  Arrange: Same as above, then a second loop.run(...)
  Act:     Verify microcompact ran on first call only
  Assert:  loop._microcompacted is True after first call

test_microcompact_skipped_when_no_old_assistant:
  Arrange: All assistant timestamps within last hour
  Act:     loop.run(...)
  Assert:  No tool result content was cleared
```

**`tests/test_metrics_collector.py`** (NEW, ~8 cases for C3/C4):

| # | Case | Asserts |
|---|------|---------|
| 1 | `test_metrics_counts_full_compact_invocations` | After 2 force-compacts, counter == 2 |
| 2 | `test_metrics_counts_snip_invocations` | After 1 snip, counter == 1 |
| 3 | `test_metrics_counts_microcompact_invocations` | After microcompact, counter == 1 |
| 4 | `test_metrics_counts_reactive_compact_invocations` | After PromptTooLong + retry, counter == 1 |
| 5 | `test_metrics_sums_externalized_bytes` | Sum equals actual bytes written to store |
| 6 | `test_metrics_records_token_estimate_per_turn` | Each `AgentStep` has matching entry in `metrics.tokens_per_turn` |
| 7 | `test_metrics_resets_per_loop_instance` | New `AgentLoop()` -> fresh counters |
| 8 | `test_loop_result_exposes_metrics_field` | `result.metrics.full_compacts >= 0` |

### 3.4 Phase D tests

**`tests/test_transcript_persist.py`** (NEW, ~6 cases):

| # | Case | Asserts |
|---|------|---------|
| 1 | `test_dump_load_roundtrip_string_content_messages` | Plain text messages round-trip |
| 2 | `test_dump_load_roundtrip_tool_call_messages` | `tool_use` blocks round-trip with `id`/`name`/`input` |
| 3 | `test_dump_load_roundtrip_tool_result_messages` | `tool_result` blocks round-trip with `persisted_path` |
| 4 | `test_dump_load_roundtrip_compact_boundary` | Compact boundary marker preserved |
| 5 | `test_dump_excludes_virtual_by_default` | `is_virtual=True` messages not written |
| 6 | `test_load_invalid_schema_raises_with_clear_message` | Missing required field -> explicit `ValueError` |

**`tests/test_resume_session.py`** (NEW, ~4 cases):

- `test_resume_continues_with_saved_compact_summary`
- `test_resume_missing_session_raises_clear_error`
- `test_resume_corrupted_session_does_not_crash_process`
- `test_save_then_resume_produces_identical_next_system_prompt`

### 3.5 End-to-end integration matrix

**`tests/test_end_to_end_long_session.py`** (NEW, 3 scenarios):

| # | Scenario | Steps | Pass criteria |
|---|----------|-------|---------------|
| 1 | Long conversation triggers full compact | REPL with 30 scripted turns x 5k chars each | `compacted == True` at least once, transcript contains `COMPACT_BOUNDARY` |
| 2 | Cross-session resume preserves summary | Session A: 10 turns + `/save foo`, exit. Session B: `--resume foo`, 5 more turns | Session B's first system prompt contains the summary text from A |
| 3 | Memory injection affects response | Pre-seed `ProjectMemory` with feedback "user prefers tabs over spaces" -> ask "write hello world" | `step.memory_injected` non-empty AND contains that snippet AND the snippet is present in `built.system` |

---

## 4. Milestones

```
M1 (2-3h) -- A1 + A3 + A4 + B1 + tests 3.1 + 3.2
  Exit gate: simple-agent --repl runs >=10 turns in tempdir;
             simple-agent memory add user foo "bar" creates JSON.
             pytest count: 392 -> >=420.

M2 (1-2h) -- C1 + C2 + tests 3.3 stress + microcompact
  Exit gate: stdout shows "compact fired (messages_summarized=N)"
             and "microcompact fired (results cleared=N)".
             pytest count: >=435.

M3 (1-2h) -- C3 + C4 + B3 + tests 3.3 metrics + 3.2 session-persist
  Exit gate: REPL /stats prints per-mechanism counters.
             pytest count: >=455.

M4 (2h)   -- D1 + D2 + D3 + tests 3.4 + 3.5 scenarios 1 & 2
  Exit gate: kill process mid-session, --resume restores summary.
             pytest count: >=475.

M5 (1h)   -- A2 + B4 + tests 3.5 scenario 3
  Exit gate: openai_cli --repl works; "记住" cue triggers save prompt.
             pytest count: >=485.
```

Total: ~8-10h, ~800-1000 LoC code + ~1000 LoC tests.

---

## 5. Execution Rules for the Implementing Session

1. **Read CLAUDE.md and README.md first.** Do not skim.
2. **Run baseline pytest** and record the exact count (expected: 392).
3. **Use TaskCreate** to track milestone tasks. Mark `in_progress`
   before starting, `completed` immediately on green.
4. **TDD strictly**: write tests first (RED, must run and fail before
   implementation), implement (GREEN), refactor.
5. **Match existing style**:
   - immutable dataclasses (`@dataclass(frozen=True)` where appropriate)
   - Protocol-based dependency injection (see `Summarizer` in
     `compact.py`)
   - never mutate inputs; return new objects
   - functions <=50 lines, files <=800 lines
   - explicit error handling, no swallowed exceptions
6. **Determinism in tests**: only use `MockProvider`; use `tmp_path`
   for filesystem; use `monkeypatch` for time/env/stdin.
7. **Verify after every task**:
   - `pytest -q` passes and count increased
   - `mypy src` clean (strict mode)
   - `ruff check src tests` clean
8. **Do not touch out-of-milestone code**. M1 must not modify metrics
   or persistence; M2 must not modify CLI flags; etc.
9. **Update CLAUDE.md** at the end of each milestone with a "P9 -- M1
   complete" style entry, mirroring the P1-P8 format.
10. **Stop and confirm with the user** before starting M2. Do not
    chain milestones autonomously.

---

## 6. Out-of-scope (explicit anti-scope)

- HTTP / WebSocket server (could come as M6, not in this plan)
- TUI (textual/rich)
- MCP server / IDE plugin
- Anthropic SDK provider (only OpenAI-compatible is currently shipped)
- Vector embeddings for `MemorySelector` (Jaccard is sufficient for
  this replica per `CLAUDE.md` self-imposed limits)
- Renaming or restructuring existing modules
- Splitting `provider.py` (777 lines, just under the 800 cap -- leave
  it for now)
