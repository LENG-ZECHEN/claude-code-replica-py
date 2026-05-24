"""ExtractMemoriesRunner: pure engine for post-conversation memory extraction.

Source mapping:
  ExtractMemoriesRunner <- auto-memory sideQuery pattern in Claude Code
  ExtractionResult      <- normalized result of one extraction run
  build_extract_prompt  <- 5-section prompt template for the extraction agent

This module is deliberately isolated from AgentLoop. It receives a Provider,
memory_dir, system_prompt, a snapshot of base_messages, and a ToolRegistry,
then runs an inner loop of at most MAX_TURNS=5 turns to decide what (if
anything) to persist. M5 will wire it into AgentLoop via a stop hook.

Security:
  - Only tools in _TOOL_WHITELIST are accepted; others return is_error=True.
  - write_memory_entry uses a fresh local ProjectMemory(memory_dir) so it
    cannot escape into the main agent's memory store.
  - Path traversal defense for write_memory_entry ids is already enforced
    inside ProjectMemory.save() via _SAFE_ENTRY_ID_PATTERN + is_relative_to().
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .coding_tools import (
    WRITE_MEMORY_ENTRY_SCHEMA,
    WRITE_MEMORY_ENTRY_TOOL_DESCRIPTION,
    WRITE_MEMORY_ENTRY_TOOL_NAME,
    write_memory_entry,
)
from .memdir import format_memory_manifest, scan_memory_files
from .memory import ProjectMemory
from .models import ToolCall
from .provider import STOP_TOOL_USE, Provider
from .tools import ToolExecutor, ToolRegistry, UnknownToolError

MAX_TURNS: int = 5

_TOOL_WHITELIST: frozenset[str] = frozenset({
    "read_file",
    "list_files",
    "search_text",
    WRITE_MEMORY_ENTRY_TOOL_NAME,
})


@dataclass(frozen=True)
class ExtractionResult:
    """Result of one ExtractMemoriesRunner.run() invocation."""
    written_paths: tuple[str, ...]  # absolute paths of .md files written
    errors: tuple[str, ...]         # runner-level errors, e.g. "max turns reached"
    turn_count: int                 # how many provider calls were made


def build_extract_prompt(
    new_message_count: int,
    existing_memories_manifest: str,
) -> str:
    """Build the 5-section extraction prompt for the extraction agent.

    Sections: opener / immediate action / types / what-not-to-save / how-to-save.
    """
    return (
        f"You are a memory extraction agent. The user's agent just finished a conversation "
        f"turn ({new_message_count} new messages). Your job is to review those messages and "
        f"decide whether anything is worth saving to long-term memory.\n\n"
        f"**Immediate action**: Review the recent messages and extract any information "
        f"that should be saved using the write_memory_entry tool.\n\n"
        f"**Memory types to consider**:\n"
        f"- `user`: information about the user (role, preferences, expertise)\n"
        f"- `feedback`: guidance given about how to behave\n"
        f"- `project`: ongoing work context, goals, decisions, deadlines\n"
        f"- `reference`: pointers to external resources, docs, tickets\n\n"
        f"**Do NOT save**: code snippets, git history, ephemeral task details, "
        f"anything already in CLAUDE.md, speculative ideas not confirmed by the user.\n\n"
        f"**How to save**: use write_memory_entry(type, id, name, description, body). "
        f"If nothing is worth saving, respond with a plain text message explaining why.\n\n"
        f"**Existing memories** (do not duplicate):\n"
        f"{existing_memories_manifest}"
    )


def _get_existing_manifest(memory_dir: Path) -> str:
    """Build the existing-memories manifest (the extraction prompt's "do not
    duplicate" list) via the canonical memdir formatter.

    Scans the ``.md`` files directly rather than reading a possibly-absent or
    stale ``MEMORY.md`` prefix (the original M4 stub), so the extractor always
    sees the real, line-complete set of existing memories.
    """
    headers = scan_memory_files(memory_dir)
    if not headers:
        return "(no memories yet)"
    return format_memory_manifest(headers)


class ExtractMemoriesRunner:
    """Pure extraction engine — no coupling to AgentLoop.

    M5 wires this into AgentLoop.run() / run_stream() via a stop hook.
    The runner holds a snapshot of base_messages (copied at construction)
    and does NOT mutate the caller's list or the main transcript.
    """

    def __init__(
        self,
        provider: Provider,
        memory_dir: Path,
        system_prompt: str,
        base_messages: list[dict[str, Any]],
        tool_registry: ToolRegistry,
    ) -> None:
        self._provider = provider
        self._memory_dir = memory_dir
        self._system_prompt = system_prompt
        self._base_messages = list(base_messages)  # immutable snapshot
        self._executor = ToolExecutor(tool_registry)
        self._tool_registry = tool_registry

    def run(self, new_message_count: int) -> ExtractionResult:
        """Run up to MAX_TURNS provider calls, writing memories as instructed."""
        manifest = _get_existing_manifest(self._memory_dir)
        prompt = build_extract_prompt(new_message_count, manifest)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        whitelist_tools = self._build_whitelist_tools()

        written_paths: list[str] = []
        errors: list[str] = []
        turn_count = 0

        for _ in range(MAX_TURNS):
            response = self._provider.call(
                system=self._system_prompt,
                messages=messages,
                tools=whitelist_tools,
            )
            turn_count += 1

            if response.stop_reason != STOP_TOOL_USE:
                break

            # Append assistant message with tool_use blocks
            assistant_content: list[dict[str, Any]] = []
            if response.text:
                assistant_content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                })
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute each tool call and collect results
            tool_results_content: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                content, is_error = self._execute_tool(tc, written_paths)
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": content,
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": tool_results_content})
        else:
            # for/else: loop exhausted all MAX_TURNS without a break
            errors.append("max turns reached")

        return ExtractionResult(
            written_paths=tuple(written_paths),
            errors=tuple(errors),
            turn_count=turn_count,
        )

    def _execute_tool(
        self,
        tc: ToolCall,
        written_paths: list[str],
    ) -> tuple[str, bool]:
        """Dispatch tool execution, enforcing the whitelist."""
        if tc.name not in _TOOL_WHITELIST:
            return (
                f"Tool '{tc.name}' is not available in the extraction context",
                True,
            )
        if tc.name == WRITE_MEMORY_ENTRY_TOOL_NAME:
            return self._execute_write_memory(tc, written_paths)
        try:
            return self._executor.execute(tc.name, tc.input)
        except UnknownToolError:
            return f"Tool '{tc.name}' is not currently registered", True

    def _execute_write_memory(
        self,
        tc: ToolCall,
        written_paths: list[str],
    ) -> tuple[str, bool]:
        """Execute write_memory_entry with a local ProjectMemory(memory_dir)."""
        local_pm = ProjectMemory(str(self._memory_dir))
        try:
            result = write_memory_entry(project_memory=local_pm, **tc.input)
            entry_id = tc.input.get("id", "")
            abs_path = str((self._memory_dir / f"{entry_id}.md").resolve())
            written_paths.append(abs_path)
            return result, False
        except Exception as exc:
            return str(exc), True

    def _build_whitelist_tools(self) -> list[dict[str, Any]]:
        """Build tool specs for the provider restricted to _TOOL_WHITELIST."""
        tools: list[dict[str, Any]] = []
        for name in sorted(_TOOL_WHITELIST):
            if name == WRITE_MEMORY_ENTRY_TOOL_NAME:
                tools.append({
                    "name": WRITE_MEMORY_ENTRY_TOOL_NAME,
                    "description": WRITE_MEMORY_ENTRY_TOOL_DESCRIPTION,
                    "input_schema": WRITE_MEMORY_ENTRY_SCHEMA,
                })
                continue
            try:
                tool = self._tool_registry.get(name)
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                })
            except Exception:
                pass  # Not registered; skip (M5 caller should register all needed tools)
        return tools


__all__ = [
    "MAX_TURNS",
    "ExtractionResult",
    "ExtractMemoriesRunner",
    "build_extract_prompt",
]
