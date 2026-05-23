"""Phase 2: data structure tests — written before implementation (TDD)."""

import dataclasses

import pytest

from simple_coding_agent.models import (
    AgentStep,
    CompactSummary,
    FileSnapshot,
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)

# --- Role / MessageType ---

def test_role_values() -> None:
    assert Role.USER == "user"
    assert Role.ASSISTANT == "assistant"
    assert Role.SYSTEM == "system"


def test_message_type_values() -> None:
    assert MessageType.TEXT == "text"
    assert MessageType.TOOL_USE == "tool_use"
    assert MessageType.TOOL_RESULT == "tool_result"
    assert MessageType.COMPACT_BOUNDARY == "compact_boundary"
    assert MessageType.ATTACHMENT == "attachment"


# --- Message ---

def test_user_factory() -> None:
    msg = Message.user("hello")
    assert msg.role == Role.USER
    assert msg.content == "hello"
    assert msg.type == MessageType.TEXT
    assert msg.uuid != ""
    assert msg.timestamp != ""
    assert not msg.is_virtual
    assert not msg.is_meta
    assert not msg.is_compact_summary


def test_assistant_factory() -> None:
    msg = Message.assistant("hi there")
    assert msg.role == Role.ASSISTANT
    assert msg.content == "hi there"
    assert msg.type == MessageType.TEXT


def test_compact_boundary_factory() -> None:
    msg = Message.compact_boundary()
    assert msg.type == MessageType.COMPACT_BOUNDARY
    assert msg.role == Role.SYSTEM
    assert msg.is_meta


def test_message_uuid_unique() -> None:
    a = Message.user("x")
    b = Message.user("x")
    assert a.uuid != b.uuid


# --- ToolCall ---

def test_tool_call_creation() -> None:
    tc = ToolCall(id="tc_001", name="read_file", input={"path": "/tmp/x.txt"})
    assert tc.id == "tc_001"
    assert tc.name == "read_file"
    assert tc.input == {"path": "/tmp/x.txt"}


def test_tool_call_input_is_dict() -> None:
    tc = ToolCall(id="x", name="echo", input={"text": "hello", "n": 3})
    assert isinstance(tc.input, dict)


# --- ToolResult ---

def test_tool_result_defaults() -> None:
    tr = ToolResult(tool_use_id="tc_001", content="file contents")
    assert tr.tool_use_id == "tc_001"
    assert tr.content == "file contents"
    assert not tr.is_error
    assert tr.persisted_path is None
    assert tr.original_size is None


def test_tool_result_error_flag() -> None:
    tr = ToolResult(tool_use_id="tc_002", content="not found", is_error=True)
    assert tr.is_error


def test_tool_result_to_api_block() -> None:
    tr = ToolResult(tool_use_id="tc_001", content="data")
    block = tr.to_api_block()
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "tc_001"
    assert block["content"] == "data"
    assert block["is_error"] is False


def test_tool_result_to_api_block_error() -> None:
    tr = ToolResult(tool_use_id="tc_003", content="oops", is_error=True)
    block = tr.to_api_block()
    assert block["is_error"] is True


# --- AgentStep ---

def test_agent_step_creation() -> None:
    user_msg = Message.user("hello")
    asst_msg = Message.assistant("hi")
    step = AgentStep(turn=1, user_message=user_msg, assistant_message=asst_msg)
    assert step.turn == 1
    assert step.tool_calls == []
    assert step.tool_results == []
    assert not step.compacted
    assert step.memory_injected == []


def test_agent_step_with_tool_calls() -> None:
    user_msg = Message.user("list files")
    asst_msg = Message.assistant("")
    tc = ToolCall(id="tc_1", name="list_files", input={"path": "."})
    tr = ToolResult(tool_use_id="tc_1", content="a.py\nb.py")
    step = AgentStep(
        turn=2,
        user_message=user_msg,
        assistant_message=asst_msg,
        tool_calls=[tc],
        tool_results=[tr],
    )
    assert len(step.tool_calls) == 1
    assert len(step.tool_results) == 1


# --- CompactSummary ---

def test_compact_summary_creation() -> None:
    s = CompactSummary(
        boundary_uuid="abc-123",
        summary_text="Primary request: read files.\nPending tasks: none.",
        messages_summarized=10,
        pre_token_count=5000,
        post_token_count=500,
    )
    assert s.boundary_uuid == "abc-123"
    assert s.messages_summarized == 10
    assert s.pre_token_count == 5000
    assert s.post_token_count == 500
    assert s.restored_files == []
    assert s.timestamp != ""


def test_compact_summary_with_restored_files() -> None:
    s = CompactSummary(
        boundary_uuid="x",
        summary_text="summary",
        messages_summarized=5,
        pre_token_count=1000,
        post_token_count=100,
        restored_files=["src/main.py", "README.md"],
    )
    assert len(s.restored_files) == 2


# --- M3: FileSnapshot ---

def test_file_snapshot_fields() -> None:
    snap = FileSnapshot(
        path="src/main.py",
        content="print('hi')",
        captured_at="2026-05-23T12:00:00+00:00",
    )
    assert snap.path == "src/main.py"
    assert snap.content == "print('hi')"
    assert snap.captured_at == "2026-05-23T12:00:00+00:00"


def test_file_snapshot_is_frozen() -> None:
    snap = FileSnapshot(path="a.py", content="x", captured_at="t")
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.content = "mutated"  # type: ignore[misc]


# --- M3: Message.attachment factory ---

def test_message_attachment_factory() -> None:
    msg = Message.attachment("src/main.py", "print('hi')")
    assert msg.role == Role.USER
    assert msg.type == MessageType.ATTACHMENT
    assert msg.is_meta is True
    assert msg.content == (
        '<recent-files>\n<file path="src/main.py">print(\'hi\')</file>\n'
        "</recent-files>"
    )


# --- M3: CompactSummary.recent_file_snapshots ---

def test_compact_summary_recent_file_snapshots_defaults_empty() -> None:
    s = CompactSummary(
        boundary_uuid="b",
        summary_text="s",
        messages_summarized=1,
        pre_token_count=10,
        post_token_count=1,
    )
    assert s.recent_file_snapshots == ()


def test_compact_summary_is_frozen() -> None:
    s = CompactSummary(
        boundary_uuid="b",
        summary_text="s",
        messages_summarized=1,
        pre_token_count=10,
        post_token_count=1,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.summary_text = "mutated"  # type: ignore[misc]


def test_compact_summary_stores_recent_file_snapshots() -> None:
    snaps = (
        FileSnapshot(path="a.py", content="A", captured_at="t1"),
        FileSnapshot(path="b.py", content="B", captured_at="t2"),
    )
    s = CompactSummary(
        boundary_uuid="b",
        summary_text="s",
        messages_summarized=1,
        pre_token_count=10,
        post_token_count=1,
        recent_file_snapshots=snaps,
    )
    assert s.recent_file_snapshots == snaps
    assert isinstance(s.recent_file_snapshots, tuple)
