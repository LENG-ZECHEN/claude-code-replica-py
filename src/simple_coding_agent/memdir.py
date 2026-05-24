"""
memdir.py — Memory directory infrastructure for sideQuery-based recall (M6+M7).

Provides the import surface for memory selection and surfacing:
  SELECT_MEMORIES_SYSTEM_PROMPT    verbatim from TS source findRelevantMemories.ts
  scan_memory_files                re-exported from memory.py
  MemoryHeader                     re-exported from memory.py
  FRONTMATTER_MAX_LINES            re-exported from memory.py
  format_memory_manifest           formats headers as MEMORY.md-style index
  collect_recent_successful_tools  reverse-scans messages for successful tools
  find_relevant_memories           4-gate selector call + Jaccard fallback (M7)
  read_memories_for_surfacing      reads files with truncation + staleness header (M7)

Source mapping:
  SELECT_MEMORIES_SYSTEM_PROMPT   <- findRelevantMemories.ts lines 18-24
  format_memory_manifest          <- formatMemoryManifest() in memoryScan.ts
  collect_recent_successful_tools <- collectRecentTools() pattern in memdir.ts
  find_relevant_memories          <- findRelevantMemories() in findRelevantMemories.ts
  read_memories_for_surfacing     <- readMemoriesForSurfacing() in memdir.ts
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from .memory import FRONTMATTER_MAX_LINES, MemoryHeader, scan_memory_files
from .models import Message, Role, ToolCall, ToolResult
from .provider import Provider, SelectorError

__all__ = [
    "FRONTMATTER_MAX_LINES",
    "MemoryHeader",
    "RecallResult",
    "SELECT_MEMORIES_SYSTEM_PROMPT",
    "collect_recent_successful_tools",
    "find_relevant_memories",
    "format_memory_manifest",
    "read_memories_for_surfacing",
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


# ---------------------------------------------------------------------------
# M7: find_relevant_memories
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecallResult:
    """Outcome of :func:`find_relevant_memories`.

    Carries the selected headers plus the diagnostics the ``memory_select``
    trace needs: whether the Jaccard fallback ran, and the scanned manifest
    size (distinct from ``len(headers)``, the selected count).
    """
    headers: list[MemoryHeader]
    fallback_used: bool
    manifest_size: int


_SESSION_BYTES_CEILING: int = 60 * 1024  # 60 KB

_SELECTOR_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"filenames": {"type": "array", "items": {"type": "string"}}},
    "required": ["filenames"],
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _jaccard_score(query: str, text: str) -> float:
    """Jaccard similarity over lowercase alphanumeric tokens."""
    q = set(_TOKEN_RE.findall(query.lower()))
    t = set(_TOKEN_RE.findall(text.lower()))
    if not q or not t:
        return 0.0
    return len(q & t) / len(q | t)


def _jaccard_fallback(
    query: str,
    headers: list[MemoryHeader],
    already_surfaced: set[str],
    n: int = 5,
) -> list[MemoryHeader]:
    """Jaccard fallback used when call_selector raises SelectorError."""
    candidates = [h for h in headers if h.id not in already_surfaced]
    if not candidates:
        return []
    scored = [
        (_jaccard_score(query, f"{h.name or ''} {h.description or ''}"), i, h)
        for i, h in enumerate(candidates)
    ]
    if all(s == 0.0 for s, _, _ in scored):
        return [h for _, _, h in scored[:n]]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [h for _, _, h in scored[:n]]


def find_relevant_memories(
    query: str,
    dir: Path,
    selector: Provider,
    *,
    already_surfaced: set[str],
    recent_tools: list[str],
    session_bytes_used: int,
    auto_memory_enabled: bool = True,
) -> RecallResult:
    """Return up to 5 relevant memories for *query* as a :class:`RecallResult`.

    Enforces 4 gates (all must pass; returns an empty result on first failure):
      1. auto_memory_enabled is True
      2. query is not empty
      3. query is multi-word (>1 word)
      4. session_bytes_used < 60 KB

    On passing all gates: calls selector.call_selector() with the
    SELECT_MEMORIES_SYSTEM_PROMPT and the manifest. Validates returned
    filenames against scan_memory_files(dir) — hallucinated filenames are
    silently dropped — and filters already_surfaced ids. Falls back to the
    Jaccard MemorySelector on SelectorError. The result records whether that
    fallback ran and the scanned manifest size, so the caller's memory_select
    trace reports real values rather than hardcoded ones.
    """
    if not auto_memory_enabled:
        return RecallResult([], False, 0)
    if not query.strip():
        return RecallResult([], False, 0)
    if len(query.split()) <= 1:
        return RecallResult([], False, 0)
    if session_bytes_used >= _SESSION_BYTES_CEILING:
        return RecallResult([], False, 0)

    headers = scan_memory_files(dir)
    if not headers:
        return RecallResult([], False, 0)  # nothing to select from
    manifest_size = len(headers)
    valid_ids = {h.id for h in headers}
    manifest = format_memory_manifest(headers)

    query_payload = f"Query: {query}\n\nAvailable memories:\n{manifest}"
    if recent_tools:
        query_payload += f"\n\nRecently-used tools: {', '.join(recent_tools)}"

    try:
        result = selector.call_selector(
            system=SELECT_MEMORIES_SYSTEM_PROMPT,
            user=query_payload,
            output_schema=_SELECTOR_OUTPUT_SCHEMA,
        )
        raw_filenames: list[str] = result.get("filenames", [])
        selected: list[MemoryHeader] = []
        header_by_id = {h.id: h for h in headers}
        for fname in raw_filenames:
            entry_id = fname.removesuffix(".md")
            if entry_id not in valid_ids:
                continue  # hallucination guard
            if entry_id in already_surfaced:
                continue
            if entry_id in header_by_id:
                selected.append(header_by_id[entry_id])
        return RecallResult(selected[:5], False, manifest_size)
    except SelectorError:
        fallback = _jaccard_fallback(query, headers, already_surfaced)
        return RecallResult(fallback, True, manifest_size)


# ---------------------------------------------------------------------------
# M7: read_memories_for_surfacing
# ---------------------------------------------------------------------------

_MAX_LINES_PER_MEMORY: int = 200
_MAX_BYTES_PER_MEMORY: int = 4096  # 4 KB


def read_memories_for_surfacing(selected: list[MemoryHeader]) -> list[str]:
    """Read memory files and return formatted strings for injection.

    For each MemoryHeader:
      - Reads ≤200 lines AND ≤4 KB of the .md file.
      - If truncated, appends "[...truncated — N lines omitted]".
      - Prefixes with a staleness-aware header based on mtime:
          "Memory (saved today):"  or  "Memory (saved N days ago):"

    Source: readMemoriesForSurfacing() in memdir.ts.
    """
    results: list[str] = []
    now_ts = time.time()

    for header in selected:
        days_ago = int((now_ts - header.mtime) / 86400)
        if days_ago == 0:
            staleness = "Memory (saved today):"
        else:
            staleness = f"Memory (saved {days_ago} days ago):"

        try:
            with open(header.path, encoding="utf-8", errors="replace") as fh:
                raw_lines = fh.readlines()
        except OSError:
            results.append(f"{staleness}\n(could not read memory file)")
            continue

        kept: list[str] = []
        total_bytes = 0
        truncated_at: int | None = None

        for i, line in enumerate(raw_lines):
            if i >= _MAX_LINES_PER_MEMORY:
                truncated_at = i
                break
            line_bytes = len(line.encode("utf-8"))
            if total_bytes + line_bytes > _MAX_BYTES_PER_MEMORY:
                truncated_at = i
                break
            kept.append(line.rstrip("\n\r"))
            total_bytes += line_bytes

        body = "\n".join(kept)
        if truncated_at is not None:
            remaining = len(raw_lines) - truncated_at
            body += f"\n[...truncated — {remaining} lines omitted]"

        results.append(f"{staleness}\n{body}")

    return results
