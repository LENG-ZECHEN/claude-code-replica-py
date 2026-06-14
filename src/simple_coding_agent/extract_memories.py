"""ExtractMemoriesRunner: thin wrapper over ForkedAgentRunner for memory extraction.

Source mapping:
  ExtractMemoriesRunner  <- auto-memory sideQuery pattern in Claude Code
  ExtractionResult       <- normalized result of one extraction run
  build_extract_prompt   <- 5-section prompt template for the extraction agent
  _TOOL_WHITELIST        <- createAutoMemCanUseTool (extractMemories.ts:171):
                            read_file / list_files / search_text unrestricted;
                            write_memory_entry confined to memory_dir.

This module is deliberately isolated from AgentLoop. It receives a Provider,
memory_dir, system_prompt, an immutable snapshot of base_messages
(list[dict[str, Any]], not Message objects — an M4 deviation), and a
ToolRegistry; .run(new_message_count) builds a ForkedAgentRunner with:
  - task_prompt = build_extract_prompt(...)
  - context_messages = the base_messages snapshot (fixes the prior bug where
    base_messages was stored but never sent to the sub-agent)
  - can_use_tool = whitelist gate: _TOOL_WHITELIST names allowed; everything
    else denied with "not available in the extraction context"
  - max_turns = MAX_TURNS (5)

Security:
  - Only tools in _TOOL_WHITELIST are accepted at runtime; others return
    is_error=True without touching the executor.
  - write_memory_entry is registered with a fresh local ProjectMemory(memory_dir)
    so extraction cannot escape into the main agent's store.  The path-traversal
    and secret-body defenses inside ProjectMemory.save() still apply.
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
from .forked_agent import ForkedAgentRunner
from .memdir import format_memory_manifest, scan_memory_files
from .memory import ProjectMemory
from .tools import Tool, ToolRegistry, UnknownToolError

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
    """Build the existing-memories manifest for the extraction prompt.

    Scans ``.md`` files directly rather than reading a possibly-absent or
    stale ``MEMORY.md`` prefix (the original M4 stub), so the extractor always
    sees the real, line-complete set of existing memories.
    """
    headers = scan_memory_files(memory_dir)
    if not headers:
        return "(no memories yet)"
    return format_memory_manifest(headers)


class ExtractMemoriesRunner:
    """Thin wrapper over ForkedAgentRunner for post-conversation memory extraction.

    M5 wires this into AgentLoop.run() / run_stream() via a stop hook.
    The runner holds a snapshot of base_messages (copied at construction)
    and does NOT mutate the caller's list or the main transcript.

    Public API is frozen:
      __init__(provider, memory_dir, system_prompt, base_messages, tool_registry)
      run(new_message_count) -> ExtractionResult
    Both signatures are consumed by extraction_hooks.py and must not change.
    """

    def __init__(
        self,
        provider: Any,
        memory_dir: Path,
        system_prompt: str,
        base_messages: list[dict[str, Any]],
        tool_registry: ToolRegistry,
    ) -> None:
        self._provider = provider
        self._memory_dir = memory_dir
        self._system_prompt = system_prompt
        self._base_messages = list(base_messages)  # immutable snapshot
        self._tool_registry = tool_registry

    def run(self, new_message_count: int) -> ExtractionResult:
        """Run up to MAX_TURNS provider calls, writing memories as instructed."""
        manifest = _get_existing_manifest(self._memory_dir)
        prompt = build_extract_prompt(new_message_count, manifest)

        written_paths: list[str] = []
        local_pm = ProjectMemory(str(self._memory_dir))

        restricted_registry = self._build_restricted_registry(written_paths, local_pm)

        def can_use_tool(name: str, inp: dict[str, Any]) -> tuple[bool, str]:
            if name in _TOOL_WHITELIST:
                return True, ""
            return False, f"Tool '{name}' is not available in the extraction context"

        forked = ForkedAgentRunner(
            provider=self._provider,
            system_prompt=self._system_prompt,
            can_use_tool=can_use_tool,
            tool_registry=restricted_registry,
            max_turns=MAX_TURNS,
        )
        # Pass base_messages as context_messages — fixes the prior bug where
        # self._base_messages was stored but never sent to the sub-agent.
        result = forked.run(
            task_prompt=prompt,
            context_messages=list(self._base_messages),
        )

        return ExtractionResult(
            written_paths=tuple(written_paths),
            errors=result.errors,
            turn_count=result.turn_count,
        )

    def _build_restricted_registry(
        self,
        written_paths: list[str],
        local_pm: ProjectMemory,
    ) -> ToolRegistry:
        """Build a ToolRegistry restricted to _TOOL_WHITELIST.

        write_memory_entry is registered with a closure over local_pm and
        written_paths so writes are confined to memory_dir and tracked.
        Other whitelist tools are copied from self._tool_registry; an
        UnknownToolError (not in registry) is silently skipped — the gate
        will deny any unexpected names at runtime.
        """
        registry = ToolRegistry()

        # Register write_memory_entry with a fresh local ProjectMemory closure.
        memory_dir = self._memory_dir

        def tracked_write(**kwargs: Any) -> str:
            result = write_memory_entry(project_memory=local_pm, **kwargs)
            entry_id = kwargs.get("id", "")
            abs_path = str((memory_dir / f"{entry_id}.md").resolve())
            written_paths.append(abs_path)
            return result

        registry.register(Tool(
            name=WRITE_MEMORY_ENTRY_TOOL_NAME,
            description=WRITE_MEMORY_ENTRY_TOOL_DESCRIPTION,
            input_schema=WRITE_MEMORY_ENTRY_SCHEMA,
            fn=tracked_write,
        ))

        # Copy read-only whitelist tools from the caller-supplied registry.
        # Narrowed from the original bare `except Exception: pass` to
        # `UnknownToolError` only — unexpected exceptions should propagate.
        read_only_names = frozenset(_TOOL_WHITELIST) - {WRITE_MEMORY_ENTRY_TOOL_NAME}
        for name in sorted(read_only_names):
            try:
                registry.register(self._tool_registry.get(name))
            except UnknownToolError:
                pass  # Not registered by caller; gate handles runtime deny

        return registry


__all__ = [
    "MAX_TURNS",
    "ExtractionResult",
    "ExtractMemoriesRunner",
    "build_extract_prompt",
]
