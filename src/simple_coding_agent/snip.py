"""SnipTool: deterministic redundant tool-result folding.

Snipping is a lightweight layer between cold-cache microcompact and full
auto-compact. It preserves transcript structure while replacing older,
redundant tool_result bodies with a stable marker.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .compact import CLEARED_TOOL_RESULT_CONTENT
from .models import Message, Role, ToolCall, ToolResult
from .trace import NullTracer, Tracer

SNIPPED_CONTENT = "[Snipped: superseded by later call]"

KEEP_LATEST_PER_PATH = frozenset({"read_file", "list_files"})

KEEP_LATEST_GLOBAL: dict[str, int] = {
    "run_shell": 3,
    "search_text": 3,
}

_COMPACTABLE_TOOLS = KEEP_LATEST_PER_PATH | frozenset(KEEP_LATEST_GLOBAL)
_PATH_THRESHOLD = 3
_TOTAL_PAIR_THRESHOLD = 10


@dataclass(frozen=True)
class _ToolInfo:
    name: str
    path: str | None = None


def _extract_path(tool_call: ToolCall) -> str | None:
    """Extract the path-like grouping key from a path-relevant tool call."""
    if tool_call.name not in KEEP_LATEST_PER_PATH:
        return None

    raw_input = getattr(tool_call, "input", None)
    if not isinstance(raw_input, dict):
        return None

    keys: tuple[str, ...] = ("path", "file_path")
    if tool_call.name == "list_files":
        keys = (*keys, "subdir")

    for key in keys:
        value = raw_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _is_already_compacted_result(content: object) -> bool:
    return content in {SNIPPED_CONTENT, CLEARED_TOOL_RESULT_CONTENT}


class SnipTool:
    """Fold redundant compactable tool_result bodies without deleting messages."""

    def __init__(self, *, tracer: Tracer | None = None) -> None:
        self._tracer: Tracer = tracer or NullTracer()

    def should_snip(self, messages: list[Message]) -> bool:
        path_counts: dict[str, int] = {}
        for msg in messages:
            if msg.role != Role.ASSISTANT or not isinstance(msg.content, list):
                continue
            for item in msg.content:
                if not isinstance(item, ToolCall):
                    continue
                path = _extract_path(item)
                if path is None:
                    continue
                path_counts[path] = path_counts.get(path, 0) + 1
                if path_counts[path] >= _PATH_THRESHOLD:
                    return True

        tool_infos = self._tool_infos_by_id(messages)
        compactable_pairs = 0
        for msg in messages:
            if not isinstance(msg.content, list):
                continue
            for item in msg.content:
                if not isinstance(item, ToolResult):
                    continue
                info = tool_infos.get(item.tool_use_id)
                if info is None:
                    continue
                if info.name in KEEP_LATEST_PER_PATH and info.path is None:
                    continue
                compactable_pairs += 1
                if compactable_pairs >= _TOTAL_PAIR_THRESHOLD:
                    return True

        return False

    def snip(self, messages: list[Message]) -> list[Message]:
        tool_infos = self._tool_infos_by_id(messages)
        positions_to_snip = self._positions_to_snip(messages, tool_infos)

        snipped: list[Message] = []
        for message_index, msg in enumerate(messages):
            if not isinstance(msg.content, list):
                snipped.append(replace(msg))
                continue

            new_content: list[ToolCall | ToolResult] = []
            for item_index, item in enumerate(msg.content):
                if isinstance(item, ToolCall):
                    new_content.append(_copy_tool_call(item))
                    continue

                if (message_index, item_index) in positions_to_snip:
                    new_content.append(replace(item, content=SNIPPED_CONTENT))
                else:
                    new_content.append(replace(item))

            snipped.append(replace(msg, content=new_content))

        self._tracer.emit(
            "snip",
            messages=len(snipped),
            snipped=len(positions_to_snip),
        )
        return snipped

    @staticmethod
    def _tool_infos_by_id(messages: list[Message]) -> dict[str, _ToolInfo | None]:
        tool_infos: dict[str, _ToolInfo | None] = {}
        for msg in messages:
            if msg.role != Role.ASSISTANT or not isinstance(msg.content, list):
                continue
            for item in msg.content:
                if not isinstance(item, ToolCall):
                    continue
                if item.name not in _COMPACTABLE_TOOLS:
                    continue
                info = _ToolInfo(
                    name=item.name,
                    path=_extract_path(item) if item.name in KEEP_LATEST_PER_PATH else None,
                )
                existing = tool_infos.get(item.id)
                if existing is None and item.id not in tool_infos:
                    tool_infos[item.id] = info
                elif existing != info:
                    tool_infos[item.id] = None
        return tool_infos

    @staticmethod
    def _positions_to_snip(
        messages: list[Message],
        tool_infos: dict[str, _ToolInfo | None],
    ) -> set[tuple[int, int]]:
        positions_to_snip: set[tuple[int, int]] = set()
        preserved_paths: set[tuple[str, str]] = set()
        preserved_global_counts: dict[str, int] = {name: 0 for name in KEEP_LATEST_GLOBAL}

        for message_index in range(len(messages) - 1, -1, -1):
            msg = messages[message_index]
            if not isinstance(msg.content, list):
                continue
            for item_index in range(len(msg.content) - 1, -1, -1):
                item = msg.content[item_index]
                if not isinstance(item, ToolResult):
                    continue
                if _is_already_compacted_result(item.content):
                    continue

                info = tool_infos.get(item.tool_use_id)
                if info is None:
                    continue

                if info.name in KEEP_LATEST_PER_PATH:
                    if info.path is None:
                        continue
                    path_key = (info.name, info.path)
                    if path_key in preserved_paths:
                        positions_to_snip.add((message_index, item_index))
                    else:
                        preserved_paths.add(path_key)
                    continue

                limit = KEEP_LATEST_GLOBAL.get(info.name)
                if limit is None:
                    continue
                count = preserved_global_counts[info.name]
                if count >= limit:
                    positions_to_snip.add((message_index, item_index))
                else:
                    preserved_global_counts[info.name] = count + 1

        return positions_to_snip


def _copy_tool_call(tool_call: ToolCall) -> ToolCall:
    raw_input = getattr(tool_call, "input", None)
    if isinstance(raw_input, dict):
        copied_input: dict[str, Any] = dict(raw_input)
        return replace(tool_call, input=copied_input)
    return replace(tool_call)


__all__ = [
    "KEEP_LATEST_GLOBAL",
    "KEEP_LATEST_PER_PATH",
    "SNIPPED_CONTENT",
    "SnipTool",
]
