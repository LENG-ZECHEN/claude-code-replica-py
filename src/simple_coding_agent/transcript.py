"""
Transcript: ordered message list with compact-boundary tracking and API normalization.

Source mapping:
  messages_after_compact_boundary <- getMessagesAfterCompactBoundary() src/utils/messages.ts:4643
  normalize_for_api               <- normalizeMessagesForAPI() src/utils/messages.ts:1989
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .models import Message, MessageType, Role, ToolCall, ToolResult

_TRANSCRIPT_VERSION = 1
_REQUIRED_MESSAGE_FIELDS = ("uuid", "role", "content", "timestamp", "type")


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

    def replace_all(self, messages: list[Message]) -> None:
        self._messages = list(messages)

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
            if msg.type in (
                MessageType.COMPACT_BOUNDARY,
                MessageType.ATTACHMENT,
                MessageType.ATTACHMENT_MEMORY,
                MessageType.ATTACHMENT_TODO_NUDGE,
                MessageType.ATTACHMENT_PLAN_MODE,
            ):
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

    # ------------------------------------------------------------------
    # Cross-process persistence (M4-D1)
    # ------------------------------------------------------------------

    def to_jsonable(
        self,
        *,
        include_virtual: bool = False,
    ) -> dict[str, Any]:
        """Return a JSON-ready dict for ``dump_json`` and ``session_store``.

        Display-only ``is_virtual`` messages are dropped by default so a
        resumed session does not replay banner state.
        """
        messages_payload = [
            _message_to_json_dict(m)
            for m in self._messages
            if include_virtual or not m.is_virtual
        ]
        return {
            "version": _TRANSCRIPT_VERSION,
            "messages": messages_payload,
        }

    @classmethod
    def from_jsonable(cls, payload: dict[str, Any]) -> Transcript:
        """Inverse of ``to_jsonable``; validates required fields."""
        if not isinstance(payload, dict):
            raise ValueError("transcript payload must be a JSON object")
        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list):
            raise ValueError("transcript payload has no 'messages' list")
        store = cls()
        for raw in raw_messages:
            if not isinstance(raw, dict):
                raise ValueError("transcript payload has a non-object message")
            store.append(_message_from_json_dict(raw))
        return store

    def dump_json(
        self,
        path: str | Path,
        *,
        include_virtual: bool = False,
    ) -> None:
        """Atomically persist the transcript to ``path`` as JSON.

        Atomic write uses ``tempfile.mkstemp`` + ``os.replace`` (same shape
        as ``SessionMemory.dump_json``); if the rename fails the prior
        snapshot remains intact.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_jsonable(include_virtual=include_virtual)
        _atomic_write_json(target, payload)

    @classmethod
    def load_json(cls, path: str | Path) -> Transcript:
        """Load a transcript snapshot from ``path``.

        Raises:
            ValueError: when the file's schema is missing a required field
                (``uuid``/``role``/``content``/``timestamp``/``type``) or
                holds an unrecognised enum value. The caller chose this
                path explicitly, so a hard failure is preferable to silent
                truncation.
            OSError / json.JSONDecodeError: re-raised; callers wrap when
                they need a soft failure.
        """
        target = Path(path)
        with open(target, encoding="utf-8") as fh:
            payload = json.load(fh)
        return cls.from_jsonable(payload)


# ---------------------------------------------------------------------------
# JSON (de)serialization helpers
# ---------------------------------------------------------------------------


def _message_to_json_dict(msg: Message) -> dict[str, Any]:
    out: dict[str, Any] = {
        "uuid": msg.uuid,
        "role": msg.role.value,
        "timestamp": msg.timestamp,
        "type": msg.type.value,
        "is_meta": msg.is_meta,
        "is_virtual": msg.is_virtual,
        "is_compact_summary": msg.is_compact_summary,
    }
    if isinstance(msg.content, str):
        out["content"] = msg.content
        return out

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
                "original_size": item.original_size,
            })
    out["content"] = blocks
    return out


def _message_from_json_dict(raw: dict[str, Any]) -> Message:
    for field_name in _REQUIRED_MESSAGE_FIELDS:
        if field_name not in raw:
            raise ValueError(
                f"transcript message missing required field {field_name!r}",
            )

    role_value = raw["role"]
    type_value = raw["type"]
    try:
        role = Role(role_value)
    except ValueError as err:
        raise ValueError(f"transcript message has unknown role {role_value!r}") from err
    try:
        msg_type = MessageType(type_value)
    except ValueError as err:
        raise ValueError(
            f"transcript message has unknown type {type_value!r}",
        ) from err

    raw_content = raw["content"]
    content: str | list[ToolCall | ToolResult]
    if isinstance(raw_content, str):
        content = raw_content
    elif isinstance(raw_content, list):
        content = [_content_block_from_json(block) for block in raw_content]
    else:
        raise ValueError(
            "transcript message 'content' must be a string or list of blocks",
        )

    return Message(
        uuid=str(raw["uuid"]),
        role=role,
        content=content,
        timestamp=str(raw["timestamp"]),
        type=msg_type,
        is_meta=bool(raw.get("is_meta", False)),
        is_virtual=bool(raw.get("is_virtual", False)),
        is_compact_summary=bool(raw.get("is_compact_summary", False)),
    )


def _atomic_write_json(target: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``target`` via tempfile + os.replace.

    Shared by ``Transcript.dump_json`` and ``session_store.save_session``
    so atomicity, fsync semantics, and cleanup behave identically across
    both persistence layers.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp_name, str(target))
    except Exception:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
        raise


def _content_block_from_json(block: Any) -> ToolCall | ToolResult:
    if not isinstance(block, dict):
        raise ValueError("transcript content block must be a JSON object")
    block_type = block.get("type")
    if block_type == "tool_use":
        for field_name in ("id", "name", "input"):
            if field_name not in block:
                raise ValueError(
                    f"tool_use block missing required field {field_name!r}",
                )
        input_value = block["input"]
        if not isinstance(input_value, dict):
            raise ValueError("tool_use block 'input' must be a JSON object")
        return ToolCall(
            id=str(block["id"]),
            name=str(block["name"]),
            input=dict(input_value),
        )
    if block_type == "tool_result":
        if "tool_use_id" not in block or "content" not in block:
            raise ValueError(
                "tool_result block missing required field "
                "'tool_use_id' or 'content'",
            )
        persisted_path = block.get("persisted_path")
        original_size = block.get("original_size")
        return ToolResult(
            tool_use_id=str(block["tool_use_id"]),
            content=str(block["content"]),
            is_error=bool(block.get("is_error", False)),
            persisted_path=(
                str(persisted_path) if persisted_path is not None else None
            ),
            original_size=(
                int(original_size) if original_size is not None else None
            ),
        )
    raise ValueError(
        f"transcript content block has unknown type {block_type!r}",
    )
