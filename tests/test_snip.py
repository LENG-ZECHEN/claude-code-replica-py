"""Tests for SnipTool redundant tool-result folding."""

from __future__ import annotations

from copy import deepcopy

from simple_coding_agent.compact import CLEARED_TOOL_RESULT_CONTENT
from simple_coding_agent.models import Message, MessageType, Role, ToolCall, ToolResult
from simple_coding_agent.snip import SNIPPED_CONTENT, SnipTool, _extract_path


def _exchange(
    tool_use_id: str,
    tool_name: str,
    content: str,
    input: object | None = None,
) -> list[Message]:
    tool_input = input if input is not None else {}
    return [
        Message(
            uuid=f"assistant-{tool_use_id}",
            role=Role.ASSISTANT,
            content=[
                ToolCall(
                    id=tool_use_id,
                    name=tool_name,
                    input=tool_input,  # type: ignore[arg-type]
                )
            ],
            timestamp="2026-01-01T00:00:00+00:00",
            type=MessageType.TOOL_USE,
        ),
        Message(
            uuid=f"user-{tool_use_id}",
            role=Role.USER,
            content=[ToolResult(tool_use_id=tool_use_id, content=content)],
            timestamp="2026-01-01T00:00:00+00:00",
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        ),
    ]


def _result_contents(messages: list[Message]) -> list[str]:
    return [
        item.content
        for msg in messages
        if isinstance(msg.content, list)
        for item in msg.content
        if isinstance(item, ToolResult)
    ]


def test_snip_keeps_latest_read_file_per_path() -> None:
    messages: list[Message] = []
    for i in range(4):
        messages.extend(
            _exchange(f"read-{i}", "read_file", f"result {i}", {"path": "a.py"})
        )

    snipped = SnipTool().snip(messages)

    assert _result_contents(snipped) == [
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        "result 3",
    ]


def test_snip_keeps_latest_per_path_multiple_paths() -> None:
    messages = [
        *_exchange("a-1", "read_file", "a old", {"path": "a.py"}),
        *_exchange("b-1", "read_file", "b old", {"path": "b.py"}),
        *_exchange("a-2", "read_file", "a latest", {"path": "a.py"}),
        *_exchange("b-2", "read_file", "b latest", {"path": "b.py"}),
    ]

    snipped = SnipTool().snip(messages)

    assert _result_contents(snipped) == [
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        "a latest",
        "b latest",
    ]


def test_snip_keeps_latest_3_run_shell() -> None:
    messages: list[Message] = []
    for i in range(6):
        messages.extend(
            _exchange(f"shell-{i}", "run_shell", f"shell result {i}", {"command": "pwd"})
        )

    snipped = SnipTool().snip(messages)

    assert _result_contents(snipped) == [
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        "shell result 3",
        "shell result 4",
        "shell result 5",
    ]


def test_snip_keeps_latest_3_search_text() -> None:
    messages: list[Message] = []
    for i in range(4):
        messages.extend(
            _exchange(
                f"search-{i}",
                "search_text",
                f"search result {i}",
                {"pattern": "needle"},
            )
        )

    snipped = SnipTool().snip(messages)

    assert _result_contents(snipped) == [
        SNIPPED_CONTENT,
        "search result 1",
        "search result 2",
        "search result 3",
    ]


def test_snip_leaves_non_compactable_tools_alone() -> None:
    messages: list[Message] = []
    for i in range(5):
        messages.extend(
            _exchange(
                f"write-{i}",
                "write_file",
                f"write result {i}",
                {"path": "a.py", "content": "x"},
            )
        )

    snipped = SnipTool().snip(messages)

    assert _result_contents(snipped) == [f"write result {i}" for i in range(5)]


def test_should_snip_path_threshold() -> None:
    two_reads = [
        *_exchange("read-1", "read_file", "one", {"path": "a.py"}),
        *_exchange("read-2", "read_file", "two", {"path": "a.py"}),
    ]
    three_reads = [
        *two_reads,
        *_exchange("read-3", "read_file", "three", {"path": "a.py"}),
    ]

    snip_tool = SnipTool()

    assert snip_tool.should_snip(two_reads) is False
    assert snip_tool.should_snip(three_reads) is True


def test_should_snip_total_threshold() -> None:
    nine_pairs: list[Message] = []
    for i in range(9):
        nine_pairs.extend(
            _exchange(f"shell-{i}", "run_shell", f"result {i}", {"command": "pwd"})
        )
    ten_pairs = [
        *nine_pairs,
        *_exchange("search-9", "search_text", "result 9", {"pattern": "needle"}),
    ]

    snip_tool = SnipTool()

    assert snip_tool.should_snip(nine_pairs) is False
    assert snip_tool.should_snip(ten_pairs) is True


def test_snip_is_immutable() -> None:
    messages = [
        *_exchange("read-1", "read_file", "one", {"path": "a.py"}),
        *_exchange("read-2", "read_file", "two", {"path": "a.py"}),
        *_exchange("read-3", "read_file", "three", {"path": "a.py"}),
    ]
    original = deepcopy(messages)

    snipped = SnipTool().snip(messages)

    assert messages == original
    assert snipped is not messages
    assert snipped != messages


def test_snip_is_idempotent() -> None:
    messages = [
        *_exchange("read-1", "read_file", "one", {"path": "a.py"}),
        *_exchange("read-2", "read_file", SNIPPED_CONTENT, {"path": "a.py"}),
        *_exchange("read-3", "read_file", CLEARED_TOOL_RESULT_CONTENT, {"path": "a.py"}),
        *_exchange("read-4", "read_file", "four", {"path": "a.py"}),
        *_exchange("shell-1", "run_shell", "one", {"command": "pwd"}),
        *_exchange("shell-2", "run_shell", "two", {"command": "pwd"}),
        *_exchange("shell-3", "run_shell", "three", {"command": "pwd"}),
        *_exchange("shell-4", "run_shell", "four", {"command": "pwd"}),
    ]
    snip_tool = SnipTool()

    once = snip_tool.snip(messages)
    twice = snip_tool.snip(once)

    assert twice == once
    assert _result_contents(twice) == [
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        CLEARED_TOOL_RESULT_CONTENT,
        "four",
        SNIPPED_CONTENT,
        "two",
        "three",
        "four",
    ]


def test_extract_path_handles_missing_or_malformed_input() -> None:
    calls = [
        ToolCall(id="missing", name="read_file", input={}),
        ToolCall(id="none", name="read_file", input=None),  # type: ignore[arg-type]
        ToolCall(id="empty", name="read_file", input={}),
        ToolCall(id="bad", name="read_file", input="bad"),  # type: ignore[arg-type]
        ToolCall(id="irrelevant", name="run_shell", input={"path": "a.py"}),
    ]
    messages = [
        block
        for call in calls
        for block in _exchange(call.id, call.name, f"content {call.id}", call.input)
    ]

    assert [_extract_path(call) for call in calls] == [None, None, None, None, None]

    snipped = SnipTool().snip(messages)

    assert _result_contents(snipped) == [
        "content missing",
        "content none",
        "content empty",
        "content bad",
        "content irrelevant",
    ]


def test_snip_keep_recent_one_folds_all_but_latest_global_result() -> None:
    """``keep_recent=1`` keeps only the most recent run_shell / search_text result.

    Default ``keep_recent=3`` would have preserved the last 3 results per tool;
    the aggressive preset (``snip_keep_recent=1``) drops everything except the
    very latest. Per-path tools still keep one latest per path independently of
    the parameter.
    """
    messages: list[Message] = []
    for i in range(4):
        messages.extend(
            _exchange(f"shell-{i}", "run_shell", f"shell {i}", {"command": "pwd"})
        )
    for i in range(3):
        messages.extend(
            _exchange(
                f"search-{i}",
                "search_text",
                f"search {i}",
                {"pattern": "needle"},
            )
        )

    snipped = SnipTool(keep_recent=1).snip(messages)

    assert _result_contents(snipped) == [
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        "shell 3",
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        "search 2",
    ]


def test_snip_rejects_invalid_keep_recent() -> None:
    """``keep_recent=0`` is meaningless (would snip everything) and must error."""
    import pytest

    with pytest.raises(ValueError):
        SnipTool(keep_recent=0)


def test_list_files_uses_actual_subdir_key_for_path_grouping() -> None:
    messages = [
        *_exchange("list-1", "list_files", "src old", {"subdir": "src"}),
        *_exchange("list-2", "list_files", "tests old", {"subdir": "tests"}),
        *_exchange("list-3", "list_files", "src latest", {"subdir": "src"}),
        *_exchange("list-4", "list_files", "tests latest", {"subdir": "tests"}),
    ]

    snipped = SnipTool().snip(messages)

    assert _result_contents(snipped) == [
        SNIPPED_CONTENT,
        SNIPPED_CONTENT,
        "src latest",
        "tests latest",
    ]
