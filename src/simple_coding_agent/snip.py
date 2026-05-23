"""SnipTool: deterministic redundant tool-result folding.

Snipping is a lightweight layer between cold-cache microcompact and full
auto-compact. It preserves transcript structure while replacing older,
redundant tool_result bodies with a stable marker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from .compact import CLEARED_TOOL_RESULT_CONTENT
from .context import ContextBudget
from .models import Message, Role, ToolCall, ToolResult
from .trace import NullTracer, Tracer

SNIPPED_CONTENT = "[Snipped: superseded by later call]"

KEEP_LATEST_PER_PATH = frozenset({"read_file", "list_files"})

# Global-quota tools: only the latest ``SnipTool.keep_recent`` results per tool
# are preserved; older ones are folded into ``SNIPPED_CONTENT``. The dict value
# (3) is informational and reflects the default; the active count at runtime
# is the SnipTool instance's ``_keep_recent`` field.
KEEP_LATEST_GLOBAL: dict[str, int] = {
    "run_shell": 3,
    "search_text": 3,
}

_DEFAULT_KEEP_RECENT = 3
_COMPACTABLE_TOOLS = KEEP_LATEST_PER_PATH | frozenset(KEEP_LATEST_GLOBAL)
_PATH_THRESHOLD = 3
_TOTAL_PAIR_THRESHOLD = 10

# Engine snip deletes microcompact-cleared (tool_use, tool_result) pairs once
# the summed estimated tokens of all such placeholders reach this threshold.
_DEFAULT_ANCIENT_CLEARED_THRESHOLD_TOKENS = 10_000


def _estimate_message_tokens(message: Message) -> int:
    """Estimate the token cost of one message via the char/4 API heuristic.

    Serializes the message in the same shape ``_normalize_messages`` uses
    (role + content blocks) so the estimate tracks what is actually sent to
    the API, then defers to ``ContextBudget.estimate_tokens``.
    """
    if isinstance(message.content, str):
        payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    else:
        blocks: list[dict[str, Any]] = []
        for item in message.content:
            if isinstance(item, ToolCall):
                blocks.append(
                    {"type": "tool_use", "id": item.id, "name": item.name, "input": item.input}
                )
            elif isinstance(item, ToolResult):
                blocks.append(item.to_api_block())
        payload = {"role": message.role.value, "content": blocks}
    return ContextBudget.estimate_tokens(json.dumps(payload))


def _cleared_messages(messages: list[Message]) -> list[tuple[int, int]]:
    """Return ``(message_index, estimated_tokens)`` for each message that holds
    at least one microcompact-cleared ToolResult, oldest-first (ascending)."""
    out: list[tuple[int, int]] = []
    for index, msg in enumerate(messages):
        if not isinstance(msg.content, list):
            continue
        if any(
            isinstance(item, ToolResult) and item.content == CLEARED_TOOL_RESULT_CONTENT
            for item in msg.content
        ):
            out.append((index, _estimate_message_tokens(msg)))
    return out


def _cleared_token_total(messages: list[Message]) -> int:
    """Sum of estimated tokens across all messages bearing a cleared ToolResult."""
    return sum(tokens for _, tokens in _cleared_messages(messages))


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

    def __init__(
        self,
        *,
        keep_recent: int = _DEFAULT_KEEP_RECENT,
        ancient_cleared_threshold_tokens: int = _DEFAULT_ANCIENT_CLEARED_THRESHOLD_TOKENS,
        tracer: Tracer | None = None,
    ) -> None:
        if keep_recent < 1:
            raise ValueError("keep_recent must be >= 1")
        if ancient_cleared_threshold_tokens < 1:
            raise ValueError("ancient_cleared_threshold_tokens must be >= 1")
        self._keep_recent = keep_recent
        self._ancient_cleared_threshold_tokens = ancient_cleared_threshold_tokens
        self._tracer: Tracer = tracer or NullTracer()

    def should_snip(self, messages: list[Message]) -> bool:
        if _cleared_token_total(messages) >= self._ancient_cleared_threshold_tokens:
            return True

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
        positions_to_snip = self._positions_to_snip(
            messages, tool_infos, keep_recent=self._keep_recent
        )
        positions_to_delete, earliest_deletion = self._deletion_plan(messages)

        snipped: list[Message] = []
        boundary_inserted = False
        for message_index, msg in enumerate(messages):
            if (
                earliest_deletion is not None
                and not boundary_inserted
                and message_index == earliest_deletion
            ):
                snipped.append(Message.snip_boundary())
                boundary_inserted = True

            if not isinstance(msg.content, list):
                snipped.append(replace(msg))
                continue

            new_content: list[ToolCall | ToolResult] = []
            for item_index, item in enumerate(msg.content):
                if (message_index, item_index) in positions_to_delete:
                    continue
                if isinstance(item, ToolCall):
                    new_content.append(_copy_tool_call(item))
                elif (message_index, item_index) in positions_to_snip:
                    new_content.append(replace(item, content=SNIPPED_CONTENT))
                else:
                    new_content.append(replace(item))

            # A message whose block list is emptied purely by deletion is
            # dropped; messages that still carry blocks survive intact.
            if msg.content and not new_content:
                continue
            snipped.append(replace(msg, content=new_content))

        self._tracer.emit(
            "snip",
            messages=len(snipped),
            snipped=len(positions_to_snip),
            deleted=len(positions_to_delete),
        )
        return snipped

    def _deletion_plan(
        self, messages: list[Message]
    ) -> tuple[set[tuple[int, int]], int | None]:
        """Compute block positions to delete and the earliest deletion index.

        Two deletion phases: (1) orphan ``tool_use`` / ``tool_result`` blocks
        whose paired counterpart is missing, deleted unconditionally; and
        (2) paired microcompact-cleared ``(tool_use, tool_result)`` blocks,
        deleted oldest-first once their summed token estimate reaches the
        configured threshold and only until it drops back below it.
        """
        use_ids: set[str] = set()
        result_ids: set[str] = set()
        use_positions: dict[str, tuple[int, int]] = {}
        for message_index, msg in enumerate(messages):
            if not isinstance(msg.content, list):
                continue
            for item_index, item in enumerate(msg.content):
                if isinstance(item, ToolCall):
                    use_ids.add(item.id)
                    use_positions[item.id] = (message_index, item_index)
                elif isinstance(item, ToolResult):
                    result_ids.add(item.tool_use_id)

        to_delete: set[tuple[int, int]] = set()

        # Phase 2: orphans (both directions).
        for message_index, msg in enumerate(messages):
            if not isinstance(msg.content, list):
                continue
            for item_index, item in enumerate(msg.content):
                if isinstance(item, ToolCall) and item.id not in result_ids:
                    to_delete.add((message_index, item_index))
                elif isinstance(item, ToolResult) and item.tool_use_id not in use_ids:
                    to_delete.add((message_index, item_index))

        # Phase 3: ancient cleared pairs, evicted oldest-first under threshold.
        cleared = _cleared_messages(messages)
        running_total = sum(tokens for _, tokens in cleared)
        if running_total >= self._ancient_cleared_threshold_tokens:
            for message_index, tokens in cleared:
                if running_total < self._ancient_cleared_threshold_tokens:
                    break
                if self._delete_cleared_pair(messages[message_index], message_index,
                                             use_positions, to_delete):
                    running_total -= tokens

        earliest_deletion = min((mi for mi, _ in to_delete), default=None)
        return to_delete, earliest_deletion

    @staticmethod
    def _delete_cleared_pair(
        msg: Message,
        message_index: int,
        use_positions: dict[str, tuple[int, int]],
        to_delete: set[tuple[int, int]],
    ) -> bool:
        """Mark every paired cleared ToolResult in ``msg`` plus its tool_use for
        deletion. Returns True if at least one pair was marked."""
        removed = False
        if not isinstance(msg.content, list):
            return False
        for item_index, item in enumerate(msg.content):
            if (
                isinstance(item, ToolResult)
                and item.content == CLEARED_TOOL_RESULT_CONTENT
                and item.tool_use_id in use_positions
            ):
                to_delete.add((message_index, item_index))
                to_delete.add(use_positions[item.tool_use_id])
                removed = True
        return removed

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
        *,
        keep_recent: int,
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

                if info.name not in KEEP_LATEST_GLOBAL:
                    continue
                count = preserved_global_counts[info.name]
                if count >= keep_recent:
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
