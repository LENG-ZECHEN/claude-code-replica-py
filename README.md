# simple_coding_agent

A minimal Python coding agent replica studying the context-management and
memory-management pipeline of Claude Code v2.1.88.

## Purpose

This project is a learning and portfolio artifact. It reproduces the core
runtime of Claude Code — context assembly, compaction, memory injection,
tool execution, and streaming provider calls — as a self-contained Python
package. The default execution path makes **no real API calls** and runs no
real shell commands.

See [`CLAUDE.md`](./CLAUDE.md) for the per-file architecture summary,
implementation roadmap, and documented limitations. See [`NOW.md`](./NOW.md)
for the current active initiative (if any).

## Key concepts replicated

| Concept | Source (Claude Code) | Python module |
|---|---|---|
| Agent loop | `src/query.ts:queryLoop()` | `loop.py` |
| Context budget + assembly | `src/services/compact/autoCompact.ts` | `context.py` |
| Tool result externalization + 200k budget | `src/utils/toolResultStorage.ts` | `tool_result_store.py` |
| Full compaction + summarizer protocol | `src/services/compact/compact.ts` | `compact.py` |
| Microcompact (cold-cache cleanup) | 60-min idle path in source | `compact.py` |
| Reactive compact on prompt-too-long | error handling in `queryLoop()` | `provider.py` + `loop.py` |
| Memory store + Jaccard relevance | `src/memdir/`, `findRelevantMemories.ts` | `memory.py` |
| CLAUDE.md injection | `src/utils/claudeMd.ts` | `claude_md.py` |
| OpenAI Chat Completions adapter | (out of scope in source) | `provider.py` |

## Project structure

```
src/simple_coding_agent/
  __init__.py             package version
  models.py               Message, ToolCall, ToolResult, Role, AgentStep, CompactSummary
  transcript.py           Transcript with compact-boundary tracking + replace_all
  tools.py                Tool, ToolRegistry, ToolExecutor, preview_result
  tool_result_store.py    ToolResultStore + ContentReplacementState (idempotent pointers, 200k cap)
  context.py              ContextBuilder, ContextBudget (CLAUDE.md prepend, memory + summary)
  memory.py               SessionMemory, ProjectMemory, MemorySelector (top-5 Jaccard)
  compact.py              ContextCompactor + Summarizer + RuleBasedSummarizer + LLMSummarizer + MicroCompactor
  provider.py             Provider protocol, MockProvider, OpenAIProvider, PromptTooLongError
  loop.py                 AgentLoop.run() / run_stream() with reactive compact + microcompact
  claude_md.py            ClaudeMdLoader (project + optional user-level)
  coding_tools.py         Safe workspace tools (list/read/write/search/run_shell, MOCK default)
  tool_registry_factory.py  build_default_registry(workspace)
  cli.py                  simple-agent (MockProvider demo)
  openai_cli.py           simple-agent-openai (real OpenAI-compatible CLI)
tests/
  Unit + integration tests across context, compaction, memory, provider,
  loop, tools, CLI, and demos. Run `pytest` for the current count.
examples/
  demo.py                      MockProvider demo (no API key, no network)
  openai_chat_demo.py          Hardened OpenAI demo (requires --confirm-api-call)
  aggressive_thresholds_demo.py  --aggressive-thresholds wiring demo (MockProvider, no network)
  stress_demo.py               Full-compact + reactive-compact stress demo (MockProvider)
  microcompact_demo.py         MicroCompactor cold-cache cleanup demo (--fresh negative path)
  visibility_full_demo.py      Real-API visibility demo — writes trace, transcript, metrics, and summary artifacts under examples/_artifacts/ (requires --confirm-api-call)
```

## Setup

```bash
cd python-replica
pip install -e ".[dev]"
pytest
```

## Console scripts

After install:

| Script | Backing module | Default behavior |
|---|---|---|
| `simple-agent` | `simple_coding_agent.cli` | MockProvider end-to-end demo in a tempdir. No API call. |
| `simple-agent-openai` | `simple_coding_agent.openai_cli` | **Calls the real OpenAI-compatible Chat Completions API.** Loads `.env` by default; pass `--no-dotenv` to skip. |

Both entry points support `--verbose` (stream `[trace] [<channel>] …` events to stderr) and `--aggressive-thresholds` (lower compact/snip/microcompact thresholds for demo-friendly behavior; prints a banner summarizing the preset).

The REPL also accepts fine-grained threshold overrides: `--microcompact-keep-recent`, `--output-headroom`, `--compact-headroom`, `--min-session-tokens` (PDF-aligned auto-compaction knobs), and `--snip-nudge-growth-tokens` (tokens of growth since the last snip that arm the model-driven `snip_history` nudge — lower it with a roomy `--max-context-tokens` to exercise model snips without auto-compact preempting them). See `simple-agent --help` / `simple-agent-openai --help` for the authoritative, current list.

Both REPLs additionally accept `--extract-memories` (enable automatic post-turn memory extraction; default off, also honoured via env `SIMPLE_AGENT_EXTRACT_MEMORIES=1`) and `--extract-throttle N` (run extraction at most once every `N` turns; default 1, also honoured via env `SIMPLE_AGENT_EXTRACT_THROTTLE`). Extraction is opt-in because it spends extra model tokens; `/stats` surfaces `extract_invocations` / `extract_writes` so the cost stays visible.

## Running the demo (safe, no API key required)

```bash
python examples/demo.py
# or, after install:
simple-agent
```

Both routes drive a `MockProvider` over a temporary workspace and produce a
structured trace plus a generated `REPORT.md`. No network call is ever made.

## Running with a real OpenAI-compatible endpoint

The OpenAI demo and CLI **will spend tokens against your configured
endpoint**. They are intentional opt-ins; treat them like any real-API tool.

```bash
# Hardened demo — refuses to call the API without an explicit flag:
python examples/openai_chat_demo.py --dry-run                # safe preflight, no network
python examples/openai_chat_demo.py --no-dotenv --dry-run    # preflight, ignore .env
python examples/openai_chat_demo.py --confirm-api-call       # actually call the API

# Non-interactive CLI — auto-loads .env and calls the API immediately:
simple-agent-openai --no-dotenv -m <model> "your task"
```

Safety guarantees:

- `examples/demo.py` and the `simple-agent` script are MockProvider-only and
  cannot reach the network.
- `examples/openai_chat_demo.py` refuses to call the API unless
  `--confirm-api-call` is passed, supports `--no-dotenv` and `--dry-run`,
  and never prints secret values (reports `present` / `missing` only).
- `simple-agent-openai` is the intentional real-task entry point and has
  no confirm-gate; pass `--no-dotenv` if you do not want `.env` auto-loaded.
- `run_shell` defaults to `ShellMode.MOCK` in `build_default_registry`; the
  `ALLOWLIST` mode is opt-in and restricted to `pwd ls cat grep python -m pytest`
  inside the workspace root.
- `.env` and `.env.*` are gitignored.

## Examples

All demos live under [`examples/`](./examples/). The MockProvider demos make
no network call and need no API key; the OpenAI demos are explicit opt-ins.

| Demo | Network | What it shows |
|---|---|---|
| [`demo.py`](./examples/demo.py) | none (MockProvider) | End-to-end loop over a tempdir; generates `REPORT.md`. |
| [`aggressive_thresholds_demo.py`](./examples/aggressive_thresholds_demo.py) | none (MockProvider) | `--aggressive-thresholds` wiring — lowers thresholds so compaction fires in short sessions. |
| [`stress_demo.py`](./examples/stress_demo.py) | none (MockProvider) | Full-compact and reactive-compact firing end-to-end on a scripted oversized transcript. |
| [`microcompact_demo.py`](./examples/microcompact_demo.py) | none (MockProvider) | MicroCompactor cold-cache cleanup on an aged transcript; `--fresh` shows the skip path. |
| [`openai_chat_demo.py`](./examples/openai_chat_demo.py) | real API (gated) | Hardened OpenAI chat demo; refuses to call the API without `--confirm-api-call`. |
| [`visibility_full_demo.py`](./examples/visibility_full_demo.py) | real API (gated) | Real-API visibility run that persists `transcript.txt`, `trace.stderr`, `metrics.json`, and `summary.md` under `examples/_artifacts/`. |

## Status and ongoing work

Current state, active initiative (if any), and last completed work are
tracked in a single place: [`NOW.md`](./NOW.md). Architecture and the
completed P-roadmap live in [`CLAUDE.md`](./CLAUDE.md).

Quality gates (run anytime to verify the project is green):

```bash
pytest                                                # full suite
mypy src                                              # strict
ruff check src tests examples/openai_chat_demo.py     # lint
python examples/demo.py                               # MockProvider demo
```

To kick off a new multi-milestone initiative, see
[`automation/RUNBOOK.md`](./automation/RUNBOOK.md).
