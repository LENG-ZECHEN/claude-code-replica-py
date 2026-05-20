# simple_coding_agent — Architecture Context

## Project Overview

`simple_coding_agent` is a Python replica of the core Claude Code query loop (v2.1.88). It reproduces the essential runtime pipeline — context assembly, compaction, memory injection, tool execution, and streaming provider calls — as a self-contained package under `src/simple_coding_agent/`. The goal is a readable, testable reference implementation: every design decision is traced back to a named source location in the original TypeScript, the default execution path makes no real API calls (MockProvider / ShellMode.MOCK), and an optional OpenAI Chat Completions adapter is provided for live testing against compatible endpoints. The project is intentionally narrow in scope; it does not replicate the Claude Code UI, the MCP server layer, or the Anthropic SDK provider.

---

## Per-File Summaries

### `models.py`
Defines the core data structures shared by every other module. `Message` is the transcript unit: it carries a `Role`, typed `content` (either a plain string or a list of `ToolCall`/`ToolResult` items), and boolean flags (`is_virtual`, `is_meta`, `is_compact_summary`) that control API serialization and UI rendering. Supporting dataclasses include `AgentStep` (one full turn record), `CompactSummary` (compaction run output), and the `MessageType` enum that distinguishes TEXT, TOOL_USE, TOOL_RESULT, COMPACT_BOUNDARY, and ATTACHMENT messages.

### `loop.py`
Contains `AgentLoop`, the central while-loop that drives one user turn from input to final answer. The two public methods — `run()` (synchronous) and `run_stream()` (streaming) — implement the same five-stage per-turn pipeline: compaction check, memory injection, context assembly, provider call, and response branching into COMPLETED / MAX_STEPS / MAX_TOKENS / MALFORMED. `AgentLoop` never raises on agent-runtime conditions; all failure modes surface as fields on the returned `LoopResult` or as `LoopStreamEvent` objects.

### `compact.py`
Implements `ContextCompactor`, which decides when the transcript exceeds the token budget and produces a `CompactSummary`. `should_compact()` compares estimated message tokens against a configurable fraction of `ContextBudget.available_tokens`; `compact()` splits the transcript at a keep-recent boundary, calls `_summarize()` on the older half, appends a compact-boundary marker, and re-appends the kept messages. `_summarize()` is a deterministic 9-section rule-based extractor; the production source uses an LLM call instead.

### `context.py`
`ContextBuilder.build()` assembles the full API payload for each agent turn in five steps: slice post-compact messages, externalize oversized tool results via `ToolResultStore`, normalize to Anthropic API dicts, trim the oldest messages until within budget, then compose the system prompt from base text, memory snippets, and compact summary. The free function `_remove_orphan_tool_results()` is called after the trim loop to drop `tool_result` blocks whose parent `tool_use` was removed, preventing API validation errors. Key dataclass: `BuiltContext`.

### `tool_result_store.py`
`ToolResultStore` externalizes tool results that exceed 50 000 characters to a temp file and replaces the in-context content with a compact `<persisted-output>` pointer (path + original_size + 2 000-char preview). `process_result()` writes the file on first call and returns the pointer; `retrieve()` reads it back. `ContentReplacementState` is defined alongside it to freeze pointer decisions so the same `tool_use_id` always maps to the same pointer string across repeated API calls, but it is not yet wired into `process_result()`.

### `memory.py`
Provides two memory stores. `SessionMemory` is ephemeral (in-process dict); `ProjectMemory` is file-backed, storing each `MemoryEntry` as a JSON file under a configurable directory and maintaining a `MEMORY.md` manifest. `ProjectMemory.save()` rejects bodies that match a secret-detection pattern and prevents path traversal via `_SAFE_ENTRY_ID_PATTERN` plus `Path.is_relative_to()`. Both stores expose `to_snippets()`, which returns all entries formatted as one-line strings for injection into the system prompt by `ContextBuilder`.

### `provider.py`
Defines the `Provider` protocol and two concrete implementations. `MockProvider` returns scripted `ProviderResponse` objects for deterministic tests. `OpenAIProvider` adapts the OpenAI Chat Completions API, converting the Anthropic-style message and tool shapes in both directions. Streaming is handled by `stream_call()`, which accumulates fragmented `tool_calls` deltas by index; if any call's arguments fail to parse, `StreamToolParseError` is raised and caught internally — all tool calls from that turn are dropped (`tool_calls=[]`, `stop_reason=STOP_END_TURN`) to avoid partial side effects. Raw malformed JSON is never echoed.

### `coding_tools.py`
Workspace-scoped file operations (`list_files`, `read_file`, `write_file`, `search_text`) and a bounded shell runner (`run_shell`). Every file op resolves paths through `resolve_workspace_path()` and rejects secret-like names via `_SECRET_BASENAME_PATTERNS`. `run_shell` defaults to `ShellMode.MOCK` (returns a deterministic stub without executing anything); `ShellMode.ALLOWLIST` actually runs the command via `subprocess.run(shell=False)` against a five-command allowlist (`pwd ls cat grep python`), with `python` restricted to `python -m pytest ...`. All violations raise `WorkspaceBoundaryError`.

---

## Known Design Gaps

- **`ContentReplacementState` defined in `tool_result_store.py` but never called in `process_result()`** — the class exists and is correct, but `ToolResultStore.process_result()` does not use it, so pointer decisions are recomputed on every call rather than being cached by `tool_use_id`.

- **`ContextCompactor._summarize()` is hardcoded rule-based logic, not injectable** — the method is a private implementation detail with no way to swap in an LLM-based summarizer without subclassing; the production source passes the summarization request to the model.

- **`AgentLoop` does not catch `prompt_too_long` API errors** — if the context assembly or provider call raises a context-window overflow error (e.g., from an unusually large system prompt), it propagates uncaught and crashes the loop rather than being handled as a graceful `MALFORMED` or `MAX_TOKENS` exit.

- **`ProjectMemory.to_snippets()` dumps all entries with no relevance filtering** — every saved memory entry is injected into every turn's system prompt regardless of topic, recency, or the current query; on a large memory store this wastes tokens and may degrade model focus.

- **No microcompact (60-min cold-cache cleanup)** — the source runs a lightweight compaction pass on sessions that have been idle for approximately 60 minutes to evict cold cache content; this idle-triggered path is not implemented.

- **No CLAUDE.md loader** — workspace-level instructions stored in a `CLAUDE.md` file are not detected or injected into the system prompt, so per-project conventions are invisible to the agent.

---

## Pending Implementation Priorities

- **P1 — Wire `ContentReplacementState` into `ToolResultStore.process_result()`** so pointer decisions are memoized by `tool_use_id` and stable across repeated context-rebuild calls within a turn.

- **P2 — Make `ContextCompactor._summarize()` injectable** by accepting an optional `summarize_fn: Callable[[list[Message]], str]` parameter so callers can supply an LLM-backed summarizer without subclassing.

- **P3 — Add `prompt_too_long` / context-overflow error handling in `AgentLoop`** with a graceful fallback (drop oldest messages and retry, or exit with `MAX_TOKENS`) so API context errors do not crash the loop.

- **P4 — Add relevance filtering to `ProjectMemory.to_snippets()`** using a keyword-match or recency window so only entries pertinent to the current query are injected into the system prompt.

- **P5 — Implement microcompact (idle cold-cache cleanup)** that triggers a lightweight compaction pass after a configurable idle period, mirroring the 60-minute idle path in the source.

- **P6 — Implement a CLAUDE.md loader** that detects `CLAUDE.md` in the workspace root (and optionally user-global config) and prepends its contents to the base system prompt before each turn.
