"""
memdir.py — Memory directory infrastructure for sideQuery-based recall (M6).

Provides the import surface M7 will use:
  SELECT_MEMORIES_SYSTEM_PROMPT  verbatim from TS source findRelevantMemories.ts
  scan_memory_files              re-exported from memory.py
  MemoryHeader                   re-exported from memory.py
  FRONTMATTER_MAX_LINES          re-exported from memory.py
  format_memory_manifest         formats headers as MEMORY.md-style index
  collect_recent_successful_tools  reverse-scans messages for successful tools

Source mapping:
  SELECT_MEMORIES_SYSTEM_PROMPT  <- findRelevantMemories.ts lines 18-24
  format_memory_manifest         <- formatMemoryManifest() in memoryScan.ts
  collect_recent_successful_tools <- collectRecentTools() pattern in memdir.ts
"""

from __future__ import annotations

from .memory import FRONTMATTER_MAX_LINES, MemoryHeader, scan_memory_files
from .models import Message, Role, ToolCall, ToolResult

__all__ = [
    "FRONTMATTER_MAX_LINES",
    "MemoryHeader",
    "SELECT_MEMORIES_SYSTEM_PROMPT",
    "collect_recent_successful_tools",
    "format_memory_manifest",
    "scan_memory_files",
]

# ---------------------------------------------------------------------------
# Verbatim system prompt — copied from findRelevantMemories.ts lines 18-24.
# DO NOT paraphrase: the "if a list of recently-used tools is provided" clause
# and the "warnings, gotchas, or known issues" carve-out are load-bearing for
# accurate memory selection.
# ---------------------------------------------------------------------------

SELECT_MEMORIES_SYSTEM_PROMPT = (
    "You are selecting memories that will be useful to Claude Code as it"
    " processes a user's query. You will be given the user's query and a list"
    " of available memory files with their filenames and descriptions.\n"
    "\n"
    "Return a list of filenames for the memories that will clearly be useful to"
    " Claude Code as it processes the user's query (up to 5). Only include"
    " memories that you are certain will be helpful based on their name and"
    " description.\n"
    "- If you are unsure if a memory will be useful in processing the user's"
    " query, then do not include it in your list. Be selective and discerning.\n"
    "- If there are no memories in the list that would clearly be useful, feel"
    " free to return an empty list.\n"
    "- If a list of recently-used tools is provided, do not select memories that"
    " are usage reference or API documentation for those tools (Claude Code is"
    " already exercising them). DO still select memories containing warnings,"
    " gotchas, or known issues about those tools — active use is exactly when"
    " those matter.\n"
)

# ---------------------------------------------------------------------------
# Manifest constants
# ---------------------------------------------------------------------------

_MANIFEST_MAX_ENTRIES = 200


# ---------------------------------------------------------------------------
# format_memory_manifest
# ---------------------------------------------------------------------------

def format_memory_manifest(headers: list[MemoryHeader]) -> str:
    """Format memory headers as a MEMORY.md-style index string.

    Each line: ``- [name](id.md) — description``
    Limited to 200 entries; appends a warning footer when truncated.
    Used to build the manifest string passed to call_selector.
    """
    lines: list[str] = []
    for header in headers[:_MANIFEST_MAX_ENTRIES]:
        name = header.name or header.id
        rel_path = f"{header.id}.md"
        line = f"- [{name}]({rel_path})"
        if header.description:
            line += f" — {header.description}"
        lines.append(line)

    result = "\n".join(lines)
    if len(headers) > _MANIFEST_MAX_ENTRIES:
        result += (
            f"\n\n> WARNING: memory manifest truncated at"
            f" {_MANIFEST_MAX_ENTRIES} entries."
        )
    return result


# ---------------------------------------------------------------------------
# collect_recent_successful_tools
# ---------------------------------------------------------------------------

def collect_recent_successful_tools(messages: list[Message]) -> list[str]:
    """Return names of tools successfully used in the most recent assistant turn.

    Reverse-scans ``messages`` from the end until the previous human (user
    text) turn.  Correlates ``ToolCall.id`` to ``ToolResult.tool_use_id`` and
    returns tool names where ``ToolResult.is_error`` is ``False``.

    Mirrors the ``collectRecentTools`` pairing pattern from memdir.ts.
    """
    tool_use_names: dict[str, str] = {}   # tool_use_id → tool_name
    tool_result_errors: dict[str, bool] = {}  # tool_use_id → is_error

    for message in reversed(messages):
        # Stop at a real human turn: USER message whose content is plain text.
        if message.role == Role.USER and isinstance(message.content, str):
            break

        if isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, ToolCall):
                    tool_use_names[item.id] = item.name
                elif isinstance(item, ToolResult):
                    tool_result_errors[item.tool_use_id] = item.is_error

    return [
        name
        for tool_use_id, name in tool_use_names.items()
        if tool_result_errors.get(tool_use_id) is False
    ]
