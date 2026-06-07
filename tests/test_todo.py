"""Tests for todo.py — TodoStatus, TodoItem, TodoNudge, render_todo_nudge_body,
count_assistant_turns_since, and the _is_* predicates.

Source mapping: mirrors TodoWriteTool.ts (lines 65-103) and the nudge logic
in attachments.ts:3212-3317 + messages.ts:3663-3678.
"""

from __future__ import annotations

import pytest

from simple_coding_agent.models import Message, MessageType, Role, ToolCall
from simple_coding_agent.todo import (
    TODO_REMINDER_TURNS,
    TodoItem,
    TodoStatus,
    _is_todo_reminder_attachment,
    _is_todo_write_call,
    count_assistant_turns_since,
    render_todo_nudge_body,
)
from simple_coding_agent.todo_tool import register_todo_write_tool
from simple_coding_agent.tools import ToolExecutor, ToolRegistry

# ---------------------------------------------------------------------------
# TodoStatus / TodoItem basics
# ---------------------------------------------------------------------------

def test_todo_status_values() -> None:
    assert TodoStatus.PENDING == "pending"
    assert TodoStatus.IN_PROGRESS == "in_progress"
    assert TodoStatus.COMPLETED == "completed"


def test_todo_item_frozen() -> None:
    item = TodoItem(content="Fix bug", status=TodoStatus.PENDING, activeForm="Fixing bug")
    with pytest.raises((AttributeError, TypeError)):
        item.content = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Schema validation via register_todo_write_tool
# ---------------------------------------------------------------------------

def _make_registry_with_todos() -> tuple[ToolRegistry, list]:
    store: list = []
    registry = ToolRegistry()
    register_todo_write_tool(
        registry,
        get_todos=lambda: list(store),
        set_todos=lambda v: store.extend(v) if not store else store.__setitem__(slice(None), v),
    )
    return registry, store


def _call_todo_write(registry: ToolRegistry, payload: dict) -> tuple[str, bool]:
    executor = ToolExecutor(registry)
    return executor.execute("todo_write", payload)


def test_schema_missing_content_rejected() -> None:
    registry, _ = _make_registry_with_todos()
    _, is_error = _call_todo_write(
        registry,
        {"todos": [{"status": "pending", "activeForm": "Doing"}]},
    )
    assert is_error


def test_schema_empty_content_rejected() -> None:
    registry, _ = _make_registry_with_todos()
    _, is_error = _call_todo_write(
        registry,
        {"todos": [{"content": "", "status": "pending", "activeForm": "Doing"}]},
    )
    assert is_error


def test_schema_bad_enum_rejected() -> None:
    registry, _ = _make_registry_with_todos()
    _, is_error = _call_todo_write(
        registry,
        {"todos": [{"content": "Task", "status": "done", "activeForm": "Doing"}]},
    )
    assert is_error


def test_schema_missing_active_form_rejected() -> None:
    registry, _ = _make_registry_with_todos()
    _, is_error = _call_todo_write(
        registry,
        {"todos": [{"content": "Task", "status": "pending"}]},
    )
    assert is_error


def test_schema_numeric_content_rejected() -> None:
    registry, _ = _make_registry_with_todos()
    _, is_error = _call_todo_write(
        registry,
        {"todos": [{"content": 42, "status": "pending", "activeForm": "Doing"}]},
    )
    assert is_error


# ---------------------------------------------------------------------------
# allDone collapse logic
# ---------------------------------------------------------------------------

def _make_registry_with_mutable_store() -> tuple[ToolRegistry, list]:
    """Registry that uses a mutable list correctly for set_todos."""
    store: list = []

    def _set_todos(v: list) -> None:
        store.clear()
        store.extend(v)

    registry = ToolRegistry()
    register_todo_write_tool(
        registry,
        get_todos=lambda: list(store),
        set_todos=_set_todos,
    )
    return registry, store


def test_all_done_collapse_empties_store() -> None:
    registry, store = _make_registry_with_mutable_store()
    executor = ToolExecutor(registry)
    payload = {
        "todos": [
            {"content": "Task A", "status": "completed", "activeForm": "Doing A"},
            {"content": "Task B", "status": "completed", "activeForm": "Doing B"},
            {"content": "Task C", "status": "completed", "activeForm": "Doing C"},
        ]
    }
    content, is_error = executor.execute("todo_write", payload)
    assert not is_error
    assert store == []


def test_partial_done_keeps_all_three() -> None:
    registry, store = _make_registry_with_mutable_store()
    executor = ToolExecutor(registry)
    payload = {
        "todos": [
            {"content": "Task A", "status": "completed", "activeForm": "Doing A"},
            {"content": "Task B", "status": "completed", "activeForm": "Doing B"},
            {"content": "Task C", "status": "pending", "activeForm": "Doing C"},
        ]
    }
    executor.execute("todo_write", payload)
    assert len(store) == 3


# ---------------------------------------------------------------------------
# render_todo_nudge_body
# ---------------------------------------------------------------------------

def test_render_empty_todos_no_echo_block() -> None:
    body = render_todo_nudge_body(())
    assert "hasn't been used recently" in body
    assert "Here are the existing contents" not in body


def test_render_populated_todos_exact_echo() -> None:
    items = (
        TodoItem(content="Fix X", status=TodoStatus.PENDING, activeForm="Fixing X"),
        TodoItem(content="Add Y", status=TodoStatus.IN_PROGRESS, activeForm="Adding Y"),
    )
    body = render_todo_nudge_body(items)
    assert "hasn't been used recently" in body
    assert "Here are the existing contents of your todo list:" in body
    assert "[1. [pending] Fix X\n2. [in_progress] Add Y]" in body


# ---------------------------------------------------------------------------
# count_assistant_turns_since
# ---------------------------------------------------------------------------

def _make_assistant_msg(text: str = "reply") -> Message:
    return Message.assistant(text)


def _make_user_msg(text: str = "hi") -> Message:
    return Message.user(text)


def test_count_zero_on_empty() -> None:
    assert count_assistant_turns_since([], lambda m: False) == 0


def test_count_only_assistant_msgs() -> None:
    msgs = [
        _make_user_msg("a"),
        _make_assistant_msg("b"),
        _make_user_msg("c"),
        _make_assistant_msg("d"),
    ]
    # predicate never fires — should count all 2 assistant msgs
    assert count_assistant_turns_since(msgs, lambda m: False) == 2


@pytest.mark.xfail(reason="thinking role not yet implemented in this replica")
def test_count_skips_thinking_messages() -> None:
    # Placeholder for forward-compat: when thinking messages are added,
    # they must be skipped in the counter (same as TS isThinkingMessage guard).
    pass


def test_count_stops_at_predicate_hit() -> None:
    msgs = [
        _make_assistant_msg("1"),
        _make_assistant_msg("2"),
        _make_assistant_msg("3"),
    ]
    # predicate hits on "2" (middle, index 1)
    def pred(m: Message) -> bool:
        return isinstance(m.content, str) and m.content == "2"
    # reversed: "3" counted, "2" matched (not counted), stop
    assert count_assistant_turns_since(msgs, pred) == 1


def test_matching_message_itself_not_counted() -> None:
    """The message that satisfies the predicate must NOT increment the counter."""
    msgs = [
        _make_assistant_msg("event"),
        _make_assistant_msg("after"),
    ]
    def pred(m: Message) -> bool:
        return isinstance(m.content, str) and m.content == "event"
    # reversed: "after" counted (1), "event" matches -> stop. count = 1
    assert count_assistant_turns_since(msgs, pred) == 1


# ---------------------------------------------------------------------------
# _is_todo_write_call / _is_todo_reminder_attachment predicates
# ---------------------------------------------------------------------------

def _make_tool_use_msg(tool_name: str) -> Message:
    tc = ToolCall(id="tu1", name=tool_name, input={})
    return Message(
        uuid="u1", role=Role.ASSISTANT, content=[tc],
        timestamp="2026-01-01T00:00:00+00:00",
        type=MessageType.TOOL_USE,
    )


def test_is_todo_write_call_true() -> None:
    msg = _make_tool_use_msg("todo_write")
    assert _is_todo_write_call(msg) is True


def test_is_todo_write_call_false_other_tool() -> None:
    msg = _make_tool_use_msg("read_file")
    assert _is_todo_write_call(msg) is False


def test_is_todo_write_call_false_text_msg() -> None:
    msg = _make_assistant_msg("just text")
    assert _is_todo_write_call(msg) is False


def test_is_todo_reminder_attachment_true() -> None:
    msg = Message.attachment_todo_nudge("<system-reminder>reminder</system-reminder>")
    assert _is_todo_reminder_attachment(msg) is True


def test_is_todo_reminder_attachment_false_memory() -> None:
    msg = Message.attachment_memory("memory content")
    assert _is_todo_reminder_attachment(msg) is False


# ---------------------------------------------------------------------------
# TODO_REMINDER_TURNS constant
# ---------------------------------------------------------------------------

def test_todo_reminder_turns_default() -> None:
    assert TODO_REMINDER_TURNS == 10
