"""
Transcript: ordered message list with compact-boundary tracking and API normalization.

Source mapping:
  messages_after_compact_boundary <- getMessagesAfterCompactBoundary() src/utils/messages.ts:4643
  normalize_for_api               <- normalizeMessagesForAPI() src/utils/messages.ts:1989
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .models import Message, MessageType, Role, ToolCall, ToolResult


class Transcript:
    """Ordered, append-only message list for a single agent session.

    The REPL holds the full history; only the post-compact slice is sent to
    the API — mirroring the design in src/query.ts where
    getMessagesAfterCompactBoundary() gates every queryLoop iteration.
    """

    def __init__(self) -> None:
        self._messages: list[Message] = []

    # ------------------------------------------------------------------
    # Basic accessors
    # ------------------------------------------------------------------

    def append(self, message: Message) -> None:
        self._messages.append(message)

    def all_messages(self) -> list[Message]:
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self) -> Iterator[Message]:
        return iter(self._messages)

    def recent(self, n: int) -> list[Message]:
        """Return the n most recent messages (empty list if n == 0)."""
        if n <= 0:
            return []
        return self._messages[-n:] if n < len(self._messages) else list(self._messages)

    # ------------------------------------------------------------------
    # Compact-boundary slicing
    # ------------------------------------------------------------------

    def last_compact_boundary_index(self) -> int:
        """Index of the most recent compact boundary, or -1 if none.

        Source: findLastCompactBoundaryIndex() in src/utils/messages.ts:4618.
        Scans backward so the LAST compaction wins when there are multiple.
        """
        for i in range(len(self._messages) - 1, -1, -1):
            if self._messages[i].type == MessageType.COMPACT_BOUNDARY:
                return i
        return -1

    def messages_after_compact_boundary(self) -> list[Message]:
        """Messages from the last compact boundary onward (boundary included).

        Source: getMessagesAfterCompactBoundary() src/utils/messages.ts:4643.
        Returns all messages when no boundary exists (first session).
        The boundary marker itself is stripped later by normalize_for_api().
        """
        idx = self.last_compact_boundary_index()
        return list(self._messages[idx:] if idx >= 0 else self._messages)

    # ------------------------------------------------------------------
    # API normalization
    # ------------------------------------------------------------------

    def normalize_for_api(self) -> list[dict[str, Any]]:
        """Convert messages to Anthropic API format.

        Mirrors normalizeMessagesForAPI() in src/utils/messages.ts:1989:
          - Drop is_virtual messages (display-only, never sent to model)
          - Drop COMPACT_BOUNDARY and ATTACHMENT typed messages
          - Drop SYSTEM-role messages (internal bookkeeping)
          - Convert ToolCall / ToolResult objects to API dicts
          - Merge consecutive messages of the same role
        """
        result: list[dict[str, Any]] = []

        for msg in self._messages:
            if msg.is_virtual:
                continue
            if msg.type in (MessageType.COMPACT_BOUNDARY, MessageType.ATTACHMENT):
                continue
            if msg.role == Role.SYSTEM:
                continue

            api_content: str | list[dict[str, Any]]
            if isinstance(msg.content, str):
                api_content = msg.content
            else:
                blocks: list[dict[str, Any]] = []
                for item in msg.content:
                    if isinstance(item, ToolCall):
                        blocks.append({
                            "type": "tool_use",
                            "id": item.id,
                            "name": item.name,
                            "input": item.input,
                        })
                    elif isinstance(item, ToolResult):
                        blocks.append(item.to_api_block())
                api_content = blocks

            api_msg: dict[str, Any] = {"role": msg.role.value, "content": api_content}

            # Merge consecutive same-role messages (source: mergeUserMessages).
            if result and result[-1]["role"] == api_msg["role"]:
                prev = result[-1]
                p, n = prev["content"], api_msg["content"]
                if isinstance(p, str) and isinstance(n, str):
                    prev["content"] = p + "\n" + n
                elif isinstance(p, list) and isinstance(n, list):
                    prev["content"] = p + n
                elif isinstance(p, str) and isinstance(n, list):
                    prev["content"] = [{"type": "text", "text": p}] + n
                else:  # list + str
                    prev["content"] = p + [{"type": "text", "text": n}]
            else:
                result.append(api_msg)

        return result

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def export(self) -> list[dict[str, Any]]:
        """Serialize all messages to plain dicts (for logging / persistence)."""
        out: list[dict[str, Any]] = []
        for msg in self._messages:
            entry: dict[str, Any] = {
                "uuid": msg.uuid,
                "role": msg.role.value,
                "timestamp": msg.timestamp,
                "type": msg.type.value,
                "is_meta": msg.is_meta,
                "is_virtual": msg.is_virtual,
                "is_compact_summary": msg.is_compact_summary,
            }
            if isinstance(msg.content, str):
                entry["content"] = msg.content
            else:
                blocks: list[dict[str, Any]] = []
                for item in msg.content:
                    if isinstance(item, ToolCall):
                        blocks.append({
                            "type": "tool_use",
                            "id": item.id,
                            "name": item.name,
                            "input": item.input,
                        })
                    elif isinstance(item, ToolResult):
                        blocks.append({
                            "type": "tool_result",
                            "tool_use_id": item.tool_use_id,
                            "content": item.content,
                            "is_error": item.is_error,
                            "persisted_path": item.persisted_path,
                        })
                entry["content"] = blocks
            out.append(entry)
        return out
