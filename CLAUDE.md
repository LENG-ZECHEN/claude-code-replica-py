# simple_coding_agent — Architecture Context

## Project Overview

`simple_coding_agent` is a Python replica of the core Claude Code query loop (v2.1.88). It reproduces the essential runtime pipeline — context assembly, compaction, memory injection, tool execution, and streaming provider calls — as a self-contained package under `src/simple_coding_agent/`. The goal is a readable, testable reference implementation: every design decision is traced back to a named source location in the original TypeScript, the default execution path makes no real API calls (MockProvider / ShellMode.MOCK), and an optional OpenAI Chat Completions adapter is provided for live testing against compatible endpoints. The project is intentionally narrow in scope; it does not replicate the Claude Code UI, the MCP server layer, or the Anthropic SDK provider.

---

## Per-File Summaries

### `models.py`
Defines the core data structures shared by every other module. `Message` is the transcript unit: it carries a `Role`, typed `content` (either a plain string or a list of `ToolCall`/`ToolResult` items), and boolean flags (`is_virtual`, `is_meta`, `is_compact_summary`) that control API serialization and UI rendering. Supporting dataclasses include `AgentStep` (one full turn record), `CompactSummary` (compaction run output), and the `MessageType` enum that distinguishes TEXT, TOOL_USE, TOOL_RESULT, COMPACT_BOUNDARY, and ATTACHMENT messages.

### `loop.py`
Contains `AgentLoop`, the central while-loop that drives one user turn from input to final answer. The two public methods — `run()` (synchronous) and `run_stream()` (streaming) — implement the same per-turn pipeline: full-compaction check → microcompact (cold cache cleanup, at most once per loop instance) → memory injection (with query-based selection for `ProjectMemory`) → context assembly → provider call → response branching into COMPLETED / MAX_STEPS / MAX_TOKENS / MALFORMED. When the provider raises `PromptTooLongError`, `AgentLoop` force-compacts and retries the same turn exactly once; a second prompt-too-long error returns `LoopStatus.MAX_TOKENS` without further retries. `AgentLoop` never raises on agent-runtime conditions; all failure modes surface as fields on the returned `LoopResult` or as `LoopStreamEvent` objects.

### `compact.py`
Implements three cooperating components: `ContextCompactor` (full compaction), `MicroCompactor` (cold-cache cleanup), and the `Summarizer` Protocol with two implementations (`RuleBasedSummarizer`, `LLMSummarizer`). `ContextCompactor.should_compact()` compares estimated tokens against a configurable fraction of `ContextBudget.available_tokens`; `compact()` splits the transcript at a keep-recent boundary, calls `self.summarizer.summarize()` on the older half, appends a compact-boundary marker, and re-appends the kept messages. `summarizer` is dependency-injected (defaults to `RuleBasedSummarizer`, the deterministic 9-section extractor previously baked into `_summarize`). `LLMSummarizer` wraps any `Provider`, builds a compact summarization prompt, and extracts content between `<summary>...</summary>` tags (falling back to full response text when tags are absent). `MicroCompactor.should_microcompact()` triggers when the latest assistant message is older than 60 minutes (or unparseable); `microcompact()` rewrites every `ToolResult` belonging to a `COMPACTABLE_TOOLS` call (`read_file`, `run_shell`, `search_text`, `list_files`) to `CLEARED_TOOL_RESULT_CONTENT`, pairing by `tool_use_id` and leaving unpaired or conflicting-duplicate IDs untouched. Both compactors return new lists / new messages and never mutate inputs.

### `context.py`
`ContextBuilder.build()` assembles the full API payload for each agent turn in five steps: slice post-compact messages, externalize oversized tool results via `ToolResultStore` (per-item 50k threshold + 200k total-budget cap, largest-first), normalize to Anthropic API dicts, trim the oldest messages until within budget, then compose the system prompt. The free function `_remove_orphan_tool_results()` is called after the trim loop to drop `tool_result` blocks whose parent `tool_use` was removed, preventing API validation errors. When `workspace_path` and a `ClaudeMdLoader` are both supplied, the loader's combined CLAUDE.md content is prepended to the base system prompt with the exact separator `"\n\n---\n\n"` before memory snippets and compact summary are appended. Empty loader output leaves the base prompt untouched. Key dataclass: `BuiltContext`.

### `tool_result_store.py`
`ToolResultStore` externalizes tool results that exceed 50 000 characters to a temp file and replaces the in-context content with a compact `<persisted-output>` pointer (path + original_size + 2 000-char preview). `process_result()` consults a `ContentReplacementState` cache first: once a `tool_use_id` has been externalized, the same pointer string is always returned regardless of the content passed in — guaranteeing prompt-cache stability across repeated context rebuilds within a turn. `process_results_batch()` runs the per-item 50k check, then enforces a `DEFAULT_TOTAL_BUDGET_CHARS = 200_000` message-level cap by externalizing the largest remaining inline items until total inline content drops back under budget. Cache / stored-record inconsistency is repaired by re-externalizing rather than crashing. `retrieve()` reads the full content back from disk.

### `claude_md.py`
`ClaudeMdLoader` reads project-level `CLAUDE.md` (workspace root) and an optional user-level fallback (default `~/.claude/CLAUDE.md`, overridable via the `user_claude_path` constructor argument so tests never touch the real user file). Project content appears first, followed by user content separated by a blank line. `OSError` during either read is trapped — the loader returns whatever did read successfully and skips caching the workspace so a transient failure does not poison subsequent calls. Successful loads are cached per `workspace_path`.

### `memory.py`
Provides two memory stores and one selector. `SessionMemory` is ephemeral (in-process dict); `ProjectMemory` is file-backed, storing each `MemoryEntry` as a JSON file under a configurable directory and maintaining a `MEMORY.md` manifest. `ProjectMemory.save()` rejects bodies that match a secret-detection pattern and prevents path traversal via `_SAFE_ENTRY_ID_PATTERN` plus `Path.is_relative_to()`. `MemorySelector` scores entries against a query using Jaccard similarity over lowercase alphanumeric tokens; `select_top_n()` returns up to `n` entries sorted by score (descending), preserves original order for ties, falls back to `entries[:n]` when all scores are zero, and never mutates the input list. `SessionMemory.to_snippets()` returns all entries unchanged; `ProjectMemory.to_snippets(query=None)` preserves the old full-dump behavior while `to_snippets(query="...")` returns the top 5 relevant entries via `MemorySelector`. `AgentLoop` passes the latest user input text as the query.

### `provider.py`
Defines the `Provider` protocol and two concrete implementations. `MockProvider` returns scripted `ProviderResponse` objects for deterministic tests. `OpenAIProvider` adapts the OpenAI Chat Completions API, converting the Anthropic-style message and tool shapes in both directions. Streaming is handled by `stream_call()`, which accumulates fragmented `tool_calls` deltas by index; if any call's arguments fail to parse, `StreamToolParseError` is raised and caught internally — all tool calls from that turn are dropped (`tool_calls=[]`, `stop_reason=STOP_END_TURN`) to avoid partial side effects. Raw malformed JSON is never echoed. Both `call()` and `stream_call()` wrap provider SDK exceptions: known context-window markers (`"prompt too long"`, `"maximum context length"`, `"context window"`, etc.) are mapped to a provider-neutral `PromptTooLongError` with the original exception preserved as `__cause__`; non-context errors propagate unchanged.

### `coding_tools.py`
Workspace-scoped file operations (`list_files`, `read_file`, `write_file`, `search_text`) and a bounded shell runner (`run_shell`). Every file op resolves paths through `resolve_workspace_path()` and rejects secret-like names via `_SECRET_BASENAME_PATTERNS`. `run_shell` defaults to `ShellMode.MOCK` (returns a deterministic stub without executing anything); `ShellMode.ALLOWLIST` actually runs the command via `subprocess.run(shell=False)` against a five-command allowlist (`pwd ls cat grep python`), with `python` restricted to `python -m pytest ...`. All violations raise `WorkspaceBoundaryError`.

---

## Implementation Roadmap (Completed P1–P6)

The six priorities originally listed in this document have all shipped. Commits are pinned for traceability; see each module's per-file summary above for the current behavior.

- **P1 — ToolResultBudget hardening** (`dbc3a86`, follow-up `01dc7ca`). `ContentReplacementState` is wired into `ToolResultStore.process_result()` so the same `tool_use_id` always returns the same pointer (prompt-cache stability). `process_results_batch()` adds a `DEFAULT_TOTAL_BUDGET_CHARS = 200_000` message-level cap that externalizes the largest remaining inline items first. Cache / stored-record inconsistency is repaired in place rather than crashing.

- **P2 — Injectable summarizer** (`1f90504`). `compact.py` exposes a `Summarizer` Protocol. The old 9-section logic moved into `RuleBasedSummarizer` (still the default); `LLMSummarizer` wraps any `Provider` and parses `<summary>...</summary>` tags from the response (falling back to full text when tags are absent). `ContextCompactor` accepts `summarizer: Summarizer | None = None`.

- **P3 — ReactiveCompact** (`eb2f7cb`). `provider.py` defines `PromptTooLongError`; `OpenAIProvider.call()` and `stream_call()` map known context-window markers and preserve the original exception as `__cause__`. `AgentLoop.run()` and `run_stream()` catch the error, force-compact, and retry the same turn exactly once; a second occurrence returns `LoopStatus.MAX_TOKENS` without further retries.

- **P4 — MemorySelector** (`226a974`). `memory.py` adds `MemorySelector` (Jaccard similarity over lowercase alphanumeric tokens; tie-stable, no input mutation, all-zero fallback to `entries[:n]`). `ProjectMemory.to_snippets(query=None)` preserves the old full-dump behavior; `to_snippets(query="...")` returns the top 5 relevant entries. `AgentLoop` passes the latest user input text as the query (never assistant or tool_result text).

- **P5 — Microcompact** (`7b71a09`). `MicroCompactor` clears `ToolResult.content` for old (≥60 min) compactable tools (`read_file`, `run_shell`, `search_text`, `list_files`) without deleting messages, pairing by `tool_use_id`. `Transcript.replace_all()` was added so `AgentLoop` can apply the rewritten message list. Microcompact runs before context assembly and at most once per loop instance.

- **P6 — CLAUDE.md loader** (`d1e8f70`). `ClaudeMdLoader` (`claude_md.py`) reads project-level `CLAUDE.md` and an optional user-level fallback, traps `OSError` safely, and caches per workspace. `ContextBuilder` accepts `workspace_path` and `claude_md_loader` as optional dependencies and prepends loaded content to the base system prompt with the exact separator `"\n\n---\n\n"`; empty loader output leaves the prompt unchanged. Tests inject a controlled `user_claude_path` so the real `~/.claude/CLAUDE.md` is never read.

---

## Current Limitations

These are intentional simplifications, not regressions, and are documented here so they are not mistaken for bugs:

- **Prompt-too-long detection is marker-based.** `provider.py` matches a fixed list of substrings against the exception text (`"context length exceeded"`, `"prompt too long"`, `"context window"`, etc.). A future provider with novel wording could escape detection (false negative); an unrelated error mentioning `"context window"` could be over-matched (false positive). Conservative by design.

- **`MemorySelector` uses lexical Jaccard only.** Entries that are semantically related but share no surface tokens with the query are scored zero. A stronger selector (embeddings or BM25) is out of scope for this replica.

- **`MicroCompactor.should_microcompact()` is conservative on malformed timestamps.** When `datetime.fromisoformat` cannot parse a stored assistant timestamp, the loader treats it as "no parseable assistant time" and triggers microcompact on the next turn. Acceptable for token cleanup since the operation is idempotent and only clears compactable tool results.

- **`ContextCompactor.compact()` re-appends kept messages after the boundary marker** rather than splicing the transcript. The pre-boundary copies remain in `Transcript.all_messages()` (and `export()`) but are filtered out by `messages_after_compact_boundary()` before reaching the API. This matches the source design and is harmless, but the transcript grows monotonically.
