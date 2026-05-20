"""Phase 2: Transcript tests — written before implementation (TDD)."""

from simple_coding_agent.models import Message, MessageType, Role, ToolCall, ToolResult
from simple_coding_agent.transcript import Transcript

# --- Append / len / iteration ---

def test_append_and_len() -> None:
    t = Transcript()
    t.append(Message.user("hello"))
    assert len(t) == 1


def test_all_messages_preserves_order() -> None:
    t = Transcript()
    t.append(Message.user("first"))
    t.append(Message.assistant("second"))
    msgs = t.all_messages()
    assert msgs[0].content == "first"
    assert msgs[1].content == "second"


def test_all_messages_returns_copy() -> None:
    t = Transcript()
    t.append(Message.user("a"))
    copy = t.all_messages()
    copy.clear()
    assert len(t) == 1  # original unchanged


# --- recent() ---

def test_recent_n_messages() -> None:
    t = Transcript()
    for i in range(5):
        t.append(Message.user(f"msg {i}"))
    recent = t.recent(3)
    assert len(recent) == 3
    assert recent[-1].content == "msg 4"


def test_recent_fewer_than_n() -> None:
    t = Transcript()
    t.append(Message.user("only one"))
    assert len(t.recent(10)) == 1


def test_recent_zero() -> None:
    t = Transcript()
    t.append(Message.user("a"))
    assert t.recent(0) == []


# --- compact boundary ---

def test_no_boundary_returns_all() -> None:
    t = Transcript()
    t.append(Message.user("a"))
    t.append(Message.assistant("b"))
    result = t.messages_after_compact_boundary()
    assert len(result) == 2


def test_boundary_slices_correctly() -> None:
    t = Transcript()
    t.append(Message.user("old 1"))
    t.append(Message.user("old 2"))
    t.append(Message.compact_boundary())
    t.append(Message.user("new 1"))
    t.append(Message.assistant("new 2"))

    result = t.messages_after_compact_boundary()
    # boundary + 2 new messages
    assert len(result) == 3
    assert result[0].type == MessageType.COMPACT_BOUNDARY
    assert result[1].content == "new 1"
    assert result[2].content == "new 2"


def test_last_boundary_wins() -> None:
    """Multiple compactions: only messages after the most recent boundary."""
    t = Transcript()
    t.append(Message.user("very old"))
    t.append(Message.compact_boundary())
    t.append(Message.user("middle"))
    t.append(Message.compact_boundary())
    t.append(Message.user("newest"))

    result = t.messages_after_compact_boundary()
    assert len(result) == 2  # second boundary + "newest"
    assert result[1].content == "newest"


# --- normalize_for_api ---

def test_normalize_basic_exchange() -> None:
    t = Transcript()
    t.append(Message.user("hello"))
    t.append(Message.assistant("hi"))
    api = t.normalize_for_api()
    assert len(api) == 2
    assert api[0]["role"] == "user"
    assert api[0]["content"] == "hello"
    assert api[1]["role"] == "assistant"
    assert api[1]["content"] == "hi"


def test_normalize_skips_virtual() -> None:
    t = Transcript()
    t.append(Message.user("real"))
    t.append(Message.user("virtual", is_virtual=True))
    t.append(Message.assistant("response"))
    api = t.normalize_for_api()
    assert len(api) == 2
    assert api[0]["content"] == "real"


def test_normalize_skips_compact_boundary() -> None:
    t = Transcript()
    t.append(Message.compact_boundary())
    t.append(Message.user("hello"))
    api = t.normalize_for_api()
    assert len(api) == 1
    assert api[0]["role"] == "user"


def test_normalize_skips_system_role() -> None:
    t = Transcript()
    t.append(Message.user("a"))
    sys_msg = Message(
        uuid="sys-1",
        role=Role.SYSTEM,
        content="internal note",
        timestamp="2024-01-01T00:00:00Z",
        type=MessageType.TEXT,
    )
    t.append(sys_msg)
    t.append(Message.assistant("response"))
    api = t.normalize_for_api()
    assert len(api) == 2


def test_normalize_merges_consecutive_user() -> None:
    t = Transcript()
    t.append(Message.user("part 1"))
    t.append(Message.user("part 2"))
    api = t.normalize_for_api()
    assert len(api) == 1
    assert "part 1" in api[0]["content"]
    assert "part 2" in api[0]["content"]


def test_normalize_tool_use_and_result() -> None:
    """Assistant tool_use followed by user tool_result — both preserved, not merged."""
    t = Transcript()
    tc = ToolCall(id="tc_1", name="read_file", input={"path": "x.py"})
    asst = Message(
        uuid="u1", role=Role.ASSISTANT, content=[tc],
        timestamp="2024-01-01T00:00:00Z", type=MessageType.TOOL_USE,
    )
    tr = ToolResult(tool_use_id="tc_1", content="print('hello')")
    user_result = Message(
        uuid="u2", role=Role.USER, content=[tr],
        timestamp="2024-01-01T00:00:01Z", type=MessageType.TOOL_RESULT, is_meta=True,
    )
    t.append(asst)
    t.append(user_result)
    api = t.normalize_for_api()
    assert len(api) == 2
    assert api[0]["content"][0]["type"] == "tool_use"
    assert api[0]["content"][0]["id"] == "tc_1"
    assert api[1]["content"][0]["type"] == "tool_result"
    assert api[1]["content"][0]["tool_use_id"] == "tc_1"


def test_normalize_meta_tool_result_included() -> None:
    """is_meta=True tool_result messages are NOT skipped — model needs to see them."""
    t = Transcript()
    tr = ToolResult(tool_use_id="tc_1", content="output")
    msg = Message(
        uuid="u1", role=Role.USER, content=[tr],
        timestamp="2024-01-01T00:00:00Z", type=MessageType.TOOL_RESULT, is_meta=True,
    )
    t.append(msg)
    api = t.normalize_for_api()
    assert len(api) == 1


# --- export ---

def test_export_basic() -> None:
    t = Transcript()
    t.append(Message.user("hello"))
    data = t.export()
    assert len(data) == 1
    assert data[0]["role"] == "user"
    assert data[0]["content"] == "hello"
    assert "uuid" in data[0]
    assert "timestamp" in data[0]


def test_export_tool_call_serialized() -> None:
    tc = ToolCall(id="tc_1", name="echo", input={"text": "hi"})
    msg = Message(
        uuid="u1", role=Role.ASSISTANT, content=[tc],
        timestamp="2024-01-01T00:00:00Z", type=MessageType.TOOL_USE,
    )
    t = Transcript()
    t.append(msg)
    data = t.export()
    assert data[0]["content"][0]["type"] == "tool_use"
    assert data[0]["content"][0]["name"] == "echo"
