"""Tests for memdir.collect_recent_successful_tools."""
from __future__ import annotations

from simple_coding_agent.models import Message, MessageType, Role, ToolCall, ToolResult


def _make_tool_use_msg(tool_id: str, tool_name: str) -> Message:
    return Message(
        uuid=f"uuid-{tool_id}",
        role=Role.ASSISTANT,
        content=[ToolCall(id=tool_id, name=tool_name, input={})],
        timestamp="2026-01-01T00:00:00",
        type=MessageType.TOOL_USE,
    )


def _make_tool_result_msg(tool_use_id: str, is_error: bool) -> Message:
    return Message(
        uuid=f"uuid-result-{tool_use_id}",
        role=Role.USER,
        content=[ToolResult(tool_use_id=tool_use_id, content="output", is_error=is_error)],
        timestamp="2026-01-01T00:00:00",
        type=MessageType.TOOL_RESULT,
    )


def _make_human_turn(text: str) -> Message:
    return Message(
        uuid="uuid-human",
        role=Role.USER,
        content=text,
        timestamp="2026-01-01T00:00:00",
        type=MessageType.TEXT,
    )


def test_collect_recent_tools_filters_errors() -> None:
    from simple_coding_agent.memdir import collect_recent_successful_tools

    messages = [
        _make_tool_use_msg("tu1", "read_file"),
        _make_tool_result_msg("tu1", is_error=False),
        _make_tool_use_msg("tu2", "search_text"),
        _make_tool_result_msg("tu2", is_error=True),
    ]
    tools = collect_recent_successful_tools(messages)
    assert "read_file" in tools
    assert "search_text" not in tools


def test_collect_recent_tools_stops_at_human_turn() -> None:
    from simple_coding_agent.memdir import collect_recent_successful_tools

    messages = [
        # Earlier turn (should NOT be included)
        _make_tool_use_msg("tu0", "list_files"),
        _make_tool_result_msg("tu0", is_error=False),
        # Human turn acts as the stop boundary
        _make_human_turn("do something"),
        # Most recent assistant turn (SHOULD be included)
        _make_tool_use_msg("tu1", "read_file"),
        _make_tool_result_msg("tu1", is_error=False),
    ]
    tools = collect_recent_successful_tools(messages)
    assert "read_file" in tools
    assert "list_files" not in tools


def test_collect_recent_tools_empty_when_no_tools() -> None:
    from simple_coding_agent.memdir import collect_recent_successful_tools

    messages = [
        _make_human_turn("hello"),
        Message(
            uuid="uuid-a",
            role=Role.ASSISTANT,
            content="Hi there!",
            timestamp="2026-01-01T00:00:00",
            type=MessageType.TEXT,
        ),
    ]
    tools = collect_recent_successful_tools(messages)
    assert tools == []
