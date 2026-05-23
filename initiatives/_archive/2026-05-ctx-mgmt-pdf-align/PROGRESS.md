# ctx-mgmt-pdf-align progress log

Cumulative milestone log for the `ctx-mgmt-pdf-align` initiative.
One block per milestone, newest at the bottom. **Append only —
machine-enforced.** `run_all_milestones.sh` exit-gate check 6 walks
`baseline_commit..HEAD`, finds every prior `[ctx-pdf/M{i}]` commit,
and verifies the corresponding `## M{i} — done YYYY-MM-DD` block still
exists in this file. Deleting or rewriting a prior block halts the loop.

<!-- No milestone blocks yet. The first real milestone (M1) appends its
     own block at exit ritual step 3, using the shape:

## M{N} — done YYYY-MM-DD

- **commit**: `<sha>` `[ctx-pdf/M{N}] <subject>`
- **tests**: <prev> → <new> (+<delta>)
- **mypy**: <status> | **ruff**: <status>
- **files changed**: `<file1>`, `<file2>`, ...
- **exit gate**: `<gate text from §2 of the milestone prompt>` → PASS (<one-line evidence>)
- **notes**: <optional, ≤1 line. Anything longer goes in HANDOFF.md.>
-->

## M1 — done 2026-05-23

- **commit**: `[ctx-pdf/M1]` compact-thresholds-and-llm-default (SHA in git log)
- **tests**: 615 → 632 (+17; +14 in test_compact.py, +3 in test_repl.py)
- **mypy**: clean (21 files) | **ruff**: clean
- **files changed**: `src/simple_coding_agent/compact.py`, `src/simple_coding_agent/cli.py`, `tests/test_compact.py`, `tests/test_repl.py`, `tests/test_loop.py`, `tests/test_metrics_collector.py`, `tests/test_microcompact_runtime.py`, `examples/microcompact_demo.py`
- **exit gate**: microcompact keep_recent=5 default preserves 5 newest compactable results; should_compact True iff `used >= max_tokens - output_headroom(12k) - compact_headroom(20k)` AND `used >= min_session_tokens(30k)`, legacy ratio preserved as 2nd trigger; ContextCompactor(provider=...) defaults to LLMSummarizer, provider=None keeps RuleBasedSummarizer → PASS (8 named gate tests + 632 green)
- **notes**: keep_recent=5 default changed runtime; 4 pre-PDF clearing assertions (test_loop/test_metrics_collector/test_microcompact_runtime + microcompact_demo) now construct keep_recent=0 per the exit-gate parenthetical.

## M2 — done 2026-05-23

- **commit**: `[ctx-pdf/M2]` engine-snip-orphan-and-ancient-pairs (SHA in git log)
- **tests**: 632 → 647 (+15; all in test_snip.py)
- **mypy**: clean (21 files) | **ruff**: clean
- **files changed**: `src/simple_coding_agent/snip.py`, `src/simple_coding_agent/models.py`, `src/simple_coding_agent/context.py`, `tests/test_snip.py`
- **exit gate**: snip() deletes orphan tool_use AND orphan tool_result blocks; deletes paired cleared (tool_use,tool_result) oldest-first once summed cleared tokens >= `ancient_cleared_threshold_tokens` (default 10_000), evicting only until below threshold; inserts exactly one `SNIP_BOUNDARY` (new MessageType + Message.snip_boundary(), is_meta=True) at earliest deletion; SNIP_BOUNDARY filtered in `_normalize_messages` beside COMPACT_BOUNDARY → PASS (647 green, +15; 13 existing snip cases unmodified)
- **notes**: orphan delete applies to all tools (API-validity GC, not P8 folding); deletion never creates new orphans so re-snip is a no-op (no double boundary).

## M3 — done 2026-05-23

- **commit**: `[ctx-pdf/M3]` autocompact-recent-files-attachment (SHA in git log)
- **tests**: 647 → 670 (+23; +7 test_models.py, +3 test_compact.py, +6 test_context.py, +7 test_loop.py)
- **mypy**: clean (21 files) | **ruff**: clean
- **files changed**: `src/simple_coding_agent/models.py`, `src/simple_coding_agent/compact.py`, `src/simple_coding_agent/context.py`, `src/simple_coding_agent/loop.py`, `tests/test_models.py`, `tests/test_compact.py`, `tests/test_context.py`, `tests/test_loop.py`
- **exit gate**: AgentLoop carries `_recent_file_snapshots: deque[FileSnapshot]` (default cap 5) populated in `_execute_one()` on read_file success (FileSnapshot frozen, path/content/captured_at); `_force_compact()` reads the deque once as a tuple and passes it into `ContextCompactor.compact(snapshots=...)` which stores it on the frozen `CompactSummary.recent_file_snapshots: tuple`; `ContextBuilder.build()` emits one ATTACHMENT user message per snapshot after the compact boundary, before kept messages, content `<recent-files>\n<file path="...">CONTENT</file>\n</recent-files>`, is_meta=True, never trimmed; `_normalize_messages()` now passes ATTACHMENT through (COMPACT_BOUNDARY/SNIP_BOUNDARY still filtered) → PASS (670 green, +23)
- **notes**: snapshot captures raw read content BEFORE externalization; newest-wins per-path eviction; snapshots intentionally NOT persisted by session_store (re-captured on read).

## M4 — done 2026-05-23

- **commit**: `[ctx-pdf/M4]` model-driven-snip-tool (SHA in git log)
- **tests**: 685 → 704 (+19; +16 test_snip_tool_model.py [new] + 12 test_loop.py + 6 test_context.py + 1 test_agent_integration.py — actual delta is +19 after one assertion in test_context.py was tightened to the new `<msg uuid>` wrap shape rather than added as a new case)
- **mypy**: clean (22 files) | **ruff**: clean
- **files changed**: `src/simple_coding_agent/snip_tool_model.py` [new], `src/simple_coding_agent/tool_registry_factory.py`, `src/simple_coding_agent/context.py`, `src/simple_coding_agent/loop.py`, `src/simple_coding_agent/cli.py`, `src/simple_coding_agent/openai_cli.py`, `tests/test_snip_tool_model.py` [new], `tests/test_loop.py`, `tests/test_context.py`, `tests/test_agent_integration.py`
- **exit gate**: pytest grown ≥15 from M3-post (685→704, +19); `snip_history` registered by `build_default_registry()` with schema `{"type":"object","properties":{"message_uuids":{"type":"array","items":{"type":"string"}}},"required":["message_uuids"]}`; invocation removes selected messages via `Transcript.replace_all(filtered)` and returns `"Snipped <N> messages"`; `context._normalize_messages()` wraps every tool_result block content in `<msg uuid="<uuid>">...</msg>` (gated on `msg.type == TOOL_RESULT`, ATTACHMENT untouched); `AgentLoop` tracks `_tokens_since_last_snip` updated after every `_handle_tool_calls()` return; when growth ≥ `snip_nudge_growth_tokens` (default 10_000) the next `ContextBuilder.build()` prepends an `is_meta=True` user message listing candidate uuids; window resets on engine snip / model snip / full compact; once `reactive_compact_attempted` flips True the nudge stays suppressed for the loop's lifetime → PASS (704 green, +19; all 7 AND-clauses backed by named tests)
- **notes**: cli.py / openai_cli.py wiring fix is the §7 closure-ownership change — transcript is now created BEFORE `build_default_registry` so the registered tool and the AgentLoop share the same Transcript instance. M4 is the LAST milestone of `ctx-mgmt-pdf-align`.
