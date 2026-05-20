# simple_coding_agent

A minimal Python coding agent replica studying context and memory management
patterns from Claude Code v2.1.88.

## Purpose

This project is a learning and portfolio artifact. It replicates the core
context management and memory management mechanisms of Claude Code in plain,
readable Python — without production features like IDE integration, streaming,
or multi-agent orchestration.

See [`docs/PYTHON_REPLICA_SPEC.md`](../docs/PYTHON_REPLICA_SPEC.md) for the
full design specification and source-to-module mapping.

## Key concepts replicated

| Concept | Source (Claude Code) | Python module |
|---|---|---|
| Agent loop | `src/query.ts:queryLoop()` | `loop.py` |
| Context budget | `src/services/compact/autoCompact.ts` | `context.py` |
| Tool result externalization | `src/utils/toolResultStorage.ts` | `tool_result_store.py` |
| Full compaction | `src/services/compact/compact.ts` | `compact.py` |
| Memory system | `src/memdir/` | `memory.py` |
| Relevant memory prefetch | `src/memdir/findRelevantMemories.ts` | `memory.py` |

## Project structure

```
src/simple_coding_agent/
  __init__.py          package version
  models.py            Message, ToolCall, ToolResult, Role (Phase 2)
  transcript.py        Transcript with compact boundary tracking (Phase 2)
  tools.py             Tool, ToolRegistry, ToolExecutor (Phase 3)
  tool_result_store.py Persist large results to disk (Phase 4)
  context.py           ContextBuilder, ContextBudget (Phase 5)
  memory.py            MemoryStore, MemorySelector (Phase 6)
  compact.py           ContextCompactor (Phase 7)
  provider.py          LLMProvider, MockProvider, AnthropicProvider (Phase 8)
  loop.py              AgentLoop (Phase 8)
  coding_tools.py      Safe workspace tools (Phase 9)
  cli.py               CLI entry point (Phase 10)
tests/
  test_import.py       Phase 1 smoke test
  ...                  (Phase 2-9 tests added incrementally)
examples/
  demo.py              End-to-end demo with MockProvider
```

## Setup

```bash
cd python-replica
pip install -e ".[dev]"
pytest
```

## Running the demo

```bash
python examples/demo.py
```

## Current status

**Phase 1 — Project skeleton** (complete)

Phases 2-12 are planned. See `docs/PYTHON_REPLICA_SPEC.md` section 18.
