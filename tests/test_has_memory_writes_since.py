"""Tests for hasMemoryWritesSince — the cursor-based write detector.

Covers: empty messages, write before cursor, write after cursor, no write.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime

from simple_coding_agent.extraction_hooks import hasMemoryWritesSince
from simple_coding_agent.models import Message, MessageType, Role, ToolCall

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_uuid() -> str:
    return str(_uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _user_msg(text: str = "hello") -> Message:
    return Message.user(text)


def _assistant_text_msg(text: str = "response") -> Message:
    return Message.assistant(text)


def _assistant_with_tool(name: str) -> Message:
    return Message(
        uuid=_new_uuid(),
        role=Role.ASSISTANT,
        content=[ToolCall(id="tc_1", name=name, input={})],
        timestamp=_now(),
        type=MessageType.TOOL_USE,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_false_on_empty_messages():
    assert hasMemoryWritesSince([], None) is False


def test_returns_false_when_no_write_at_all():
    """Transcript has messages but none call write_memory_entry."""
    msgs = [_user_msg(), _assistant_text_msg()]
    assert hasMemoryWritesSince(msgs, None) is False


def test_returns_true_when_write_after_cursor():
    """write_memory_entry appears after the cursor position — should return True."""
    anchor = _user_msg("first")
    write_msg = _assistant_with_tool("write_memory_entry")
    msgs = [anchor, write_msg]
    # cursor points to anchor; write_msg is after → True
    assert hasMemoryWritesSince(msgs, anchor.uuid) is True


def test_returns_false_when_write_before_cursor():
    """write_memory_entry appears before the cursor — should return False."""
    write_msg = _assistant_with_tool("write_memory_entry")
    anchor = _user_msg("later message")
    msgs = [write_msg, anchor]
    # cursor points to anchor; write_msg is before → False
    assert hasMemoryWritesSince(msgs, anchor.uuid) is False


def test_returns_false_when_write_only_at_cursor_uuid():
    """The message AT the cursor position is not 'after' it."""
    write_msg = _assistant_with_tool("write_memory_entry")
    msgs = [write_msg]
    # cursor is exactly at write_msg → not after
    assert hasMemoryWritesSince(msgs, write_msg.uuid) is False


def test_returns_false_with_none_cursor_and_no_write():
    """None cursor means scan from the beginning; no write_memory_entry → False."""
    msgs = [_user_msg(), _assistant_text_msg()]
    assert hasMemoryWritesSince(msgs, None) is False


def test_returns_true_with_none_cursor_and_write_present():
    """None cursor scans from the beginning; write_memory_entry present → True."""
    write_msg = _assistant_with_tool("write_memory_entry")
    msgs = [_user_msg(), write_msg]
    assert hasMemoryWritesSince(msgs, None) is True
