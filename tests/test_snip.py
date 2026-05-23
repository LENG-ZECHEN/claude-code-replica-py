"""Tests for SnipTool redundant tool-result folding."""

from __future__ import annotations

from copy import deepcopy

from simple_coding_agent.compact import CLEARED_TOOL_RESULT_CONTENT
from simple_coding_agent.context import _normalize_messages
from simple_coding_agent.models import Message, MessageType, Role, ToolCall, ToolResult
from simple_coding_agent.snip import (
    SNIPPED_CONTENT,
    SnipTool,
    _cleared_token_total,
    _estimate_message_tokens,
    _extract_path,
)


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


# ---------------------------------------------------------------------------
# M2: orphan deletion, ancient cleared-pair deletion, SNIP_BOUNDARY
# ---------------------------------------------------------------------------

def _assistant_tool_use(tool_use_id: str, tool_name: str, input: object) -> Message:
    """A lone assistant tool_use message (no paired tool_result)."""
    return Message(
        uuid=f"assistant-{tool_use_id}",
        role=Role.ASSISTANT,
        content=[ToolCall(id=tool_use_id, name=tool_name, input=input)],  # type: ignore[arg-type]
        timestamp="2026-01-01T00:00:00+00:00",
        type=MessageType.TOOL_USE,
    )


def _user_tool_result(tool_use_id: str, content: str) -> Message:
    """A lone user tool_result message (no paired tool_use)."""
    return Message(
        uuid=f"user-{tool_use_id}",
        role=Role.USER,
        content=[ToolResult(tool_use_id=tool_use_id, content=content)],
        timestamp="2026-01-01T00:00:00+00:00",
        type=MessageType.TOOL_RESULT,
        is_meta=True,
    )


def _cleared_exchange(tool_use_id: str) -> list[Message]:
    """A paired exchange whose tool_result content is the microcompact placeholder."""
    return _exchange(
        tool_use_id, "read_file", CLEARED_TOOL_RESULT_CONTENT, {"path": f"{tool_use_id}.py"}
    )


def _uuids(messages: list[Message]) -> list[str]:
    return [m.uuid for m in messages]


def test_snip_deletes_orphan_tool_use() -> None:
    """A tool_use whose paired tool_result is missing is deleted (not folded)."""
    messages = [
        *_exchange("read-1", "read_file", "kept", {"path": "a.py"}),
        _assistant_tool_use("orphan-use", "read_file", {"path": "b.py"}),
    ]

    snipped = SnipTool().snip(messages)

    assert "assistant-orphan-use" not in _uuids(snipped)
    assert _result_contents(snipped) == ["kept"]


def test_snip_deletes_orphan_tool_result() -> None:
    """A tool_result whose paired tool_use is missing is deleted (not folded)."""
    messages = [
        *_exchange("read-1", "read_file", "kept", {"path": "a.py"}),
        _user_tool_result("orphan-res", "dangling"),
    ]

    snipped = SnipTool().snip(messages)

    assert "user-orphan-res" not in _uuids(snipped)
    assert _result_contents(snipped) == ["kept"]


def test_snip_deletes_orphans_both_directions() -> None:
    """Orphan tool_use and orphan tool_result are both removed in one pass."""
    messages = [
        _assistant_tool_use("orphan-use", "run_shell", {"command": "pwd"}),
        *_exchange("read-1", "read_file", "kept", {"path": "a.py"}),
        _user_tool_result("orphan-res", "dangling"),
    ]

    snipped = SnipTool().snip(messages)

    remaining = _uuids(snipped)
    assert "assistant-orphan-use" not in remaining
    assert "user-orphan-res" not in remaining
    assert _result_contents(snipped) == ["kept"]


def test_snip_drops_one_orphan_block_keeps_sibling_in_same_message() -> None:
    """When an assistant message has two tool_use blocks and only one is an
    orphan, only the orphan block is dropped; the message and its paired block
    survive."""
    paired_use = ToolCall(id="paired", name="read_file", input={"path": "a.py"})
    orphan_use = ToolCall(id="orphan", name="read_file", input={"path": "b.py"})
    messages = [
        Message(
            uuid="multi-use",
            role=Role.ASSISTANT,
            content=[paired_use, orphan_use],
            timestamp="2026-01-01T00:00:00+00:00",
            type=MessageType.TOOL_USE,
        ),
        _user_tool_result("paired", "paired result"),
    ]

    snipped = SnipTool().snip(messages)

    surviving = [m for m in snipped if m.uuid == "multi-use"]
    assert len(surviving) == 1
    use_ids = [
        item.id
        for item in surviving[0].content
        if isinstance(item, ToolCall)
    ]
    assert use_ids == ["paired"]


def test_snip_keeps_adjacent_text_message_when_tool_use_deleted() -> None:
    """A plain assistant text message adjacent to a deleted orphan tool_use is
    preserved (string content is never a deletion carrier)."""
    text_msg = Message(
        uuid="assistant-text",
        role=Role.ASSISTANT,
        content="I will read the file.",
        timestamp="2026-01-01T00:00:00+00:00",
        type=MessageType.TEXT,
    )
    messages = [
        text_msg,
        _assistant_tool_use("orphan-use", "read_file", {"path": "b.py"}),
    ]

    snipped = SnipTool().snip(messages)

    assert "assistant-text" in _uuids(snipped)
    assert "assistant-orphan-use" not in _uuids(snipped)


def test_snip_deletes_all_cleared_pairs_when_threshold_low() -> None:
    """With a low threshold, eviction continues until no cleared placeholders
    remain — every paired (tool_use, tool_result) is deleted."""
    messages: list[Message] = []
    for i in range(4):
        messages.extend(_cleared_exchange(f"ancient-{i}"))

    # threshold=1 < per-message estimate, so eviction only stops at zero.
    snip_tool = SnipTool(ancient_cleared_threshold_tokens=1)

    snipped = snip_tool.snip(messages)

    # Every cleared pair (tool_use + tool_result) is gone; only the boundary
    # marker remains.
    assert _result_contents(snipped) == []
    assert all(
        not (isinstance(m.content, list) and any(isinstance(i, ToolCall) for i in m.content))
        for m in snipped
    )


def test_snip_keeps_ancient_cleared_pairs_below_threshold() -> None:
    """Below the threshold, cleared pairs are left untouched (no deletion)."""
    messages: list[Message] = []
    for i in range(4):
        messages.extend(_cleared_exchange(f"ancient-{i}"))

    total = _cleared_token_total(messages)
    snip_tool = SnipTool(ancient_cleared_threshold_tokens=total + 1)

    snipped = snip_tool.snip(messages)

    assert _result_contents(snipped) == [CLEARED_TOOL_RESULT_CONTENT] * 4
    # Nothing deleted -> no boundary marker inserted.
    assert all(m.type != MessageType.SNIP_BOUNDARY for m in snipped)


def test_snip_evicts_oldest_cleared_pairs_first_until_below_threshold() -> None:
    """Oldest cleared pairs are deleted first, stopping as soon as the remaining
    cleared tokens drop below the threshold."""
    messages: list[Message] = []
    for i in range(3):
        messages.extend(_cleared_exchange(f"ancient-{i}"))

    per_msg = _estimate_message_tokens(messages[1])  # one cleared user message
    # Threshold between 1x and 2x per-message estimate: delete oldest 2, keep newest.
    threshold = per_msg + 1
    snip_tool = SnipTool(ancient_cleared_threshold_tokens=threshold)

    snipped = snip_tool.snip(messages)

    # Newest cleared pair survives; its tool_use and tool_result remain.
    remaining = _uuids(snipped)
    assert "user-ancient-2" in remaining
    assert "assistant-ancient-2" in remaining
    assert "user-ancient-0" not in remaining
    assert "user-ancient-1" not in remaining
    assert _result_contents(snipped) == [CLEARED_TOOL_RESULT_CONTENT]


def test_snip_inserts_one_boundary_at_earliest_deletion() -> None:
    """A snip that deletes inserts exactly one SNIP_BOUNDARY at the position of
    the earliest deletion."""
    messages = [
        *_exchange("read-1", "read_file", "kept", {"path": "a.py"}),
        _user_tool_result("orphan-res", "dangling"),
        *_exchange("read-2", "read_file", "kept too", {"path": "b.py"}),
    ]

    snipped = SnipTool().snip(messages)

    boundaries = [m for m in snipped if m.type == MessageType.SNIP_BOUNDARY]
    assert len(boundaries) == 1
    boundary_index = snipped.index(boundaries[0])
    # The orphan result was the 3rd message (index 2); boundary lands there,
    # i.e. immediately after the first kept read-1 exchange (2 messages).
    assert boundary_index == 2
    assert boundaries[0].is_meta is True
    assert boundaries[0].role == Role.SYSTEM


def test_snip_no_boundary_when_nothing_deleted() -> None:
    """A pure fold (no orphans, no ancient pairs) inserts no SNIP_BOUNDARY."""
    messages: list[Message] = []
    for i in range(4):
        messages.extend(
            _exchange(f"read-{i}", "read_file", f"result {i}", {"path": "a.py"})
        )

    snipped = SnipTool().snip(messages)

    assert all(m.type != MessageType.SNIP_BOUNDARY for m in snipped)


def test_snip_with_deletion_is_idempotent_no_double_boundary() -> None:
    """Re-snipping an already-snipped transcript is a no-op: no new deletions
    and no second SNIP_BOUNDARY."""
    messages = [
        *_exchange("read-1", "read_file", "kept", {"path": "a.py"}),
        _user_tool_result("orphan-res", "dangling"),
        _assistant_tool_use("orphan-use", "run_shell", {"command": "pwd"}),
    ]
    snip_tool = SnipTool()

    once = snip_tool.snip(messages)
    twice = snip_tool.snip(once)

    assert twice == once
    assert sum(1 for m in twice if m.type == MessageType.SNIP_BOUNDARY) == 1


def test_snip_boundary_filtered_from_api_normalization() -> None:
    """SNIP_BOUNDARY messages are stripped by _normalize_messages, like
    COMPACT_BOUNDARY."""
    messages = [
        Message.user("hello"),
        Message.snip_boundary(),
        Message.assistant("hi"),
    ]

    api = _normalize_messages(messages)

    assert [m["role"] for m in api] == ["user", "assistant"]
    assert all("History snipped" not in str(m["content"]) for m in api)


def test_should_snip_cleared_token_threshold_branch() -> None:
    """should_snip returns True once cleared placeholder tokens reach the
    threshold, even with no fold-worthy or pair-count trigger."""
    messages = [
        *_cleared_exchange("ancient-0"),
        *_cleared_exchange("ancient-1"),
    ]
    total = _cleared_token_total(messages)

    assert SnipTool(ancient_cleared_threshold_tokens=total + 1).should_snip(messages) is False
    assert SnipTool(ancient_cleared_threshold_tokens=total).should_snip(messages) is True


def test_snip_rejects_invalid_ancient_threshold() -> None:
    import pytest

    with pytest.raises(ValueError):
        SnipTool(ancient_cleared_threshold_tokens=0)


def test_snip_boundary_factory_properties() -> None:
    boundary = Message.snip_boundary()

    assert boundary.type == MessageType.SNIP_BOUNDARY
    assert boundary.role == Role.SYSTEM
    assert boundary.is_meta is True
