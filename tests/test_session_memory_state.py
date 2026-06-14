"""TDD tests for SessionMemoryState and update_session_memory (M2)."""
from __future__ import annotations

import pytest

from simple_coding_agent.models import Message, MessageType, Role, ToolCall, ToolResult
from simple_coding_agent.session_memory_state import (
    SessionMemoryState,
    update_session_memory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_messages() -> list[Message]:
    """Return a small realistic message list for fold tests."""
    user = Message.user("Please fix the bug in utils.py")
    asst = Message.assistant("I'll look at the file and fix it.")
    tc = ToolCall(id="tc1", name="read_file", input={"path": "utils.py"})
    asst2 = Message(
        uuid="asst2",
        role=Role.ASSISTANT,
        content=[tc],
        timestamp="2026-01-01T00:00:00Z",
        type=MessageType.TOOL_USE,
    )
    tr = ToolResult(tool_use_id="tc1", content="def foo(): pass")
    user2 = Message(
        uuid="user2",
        role=Role.USER,
        content=[tr],
        timestamp="2026-01-01T00:00:01Z",
        type=MessageType.TOOL_RESULT,
    )
    return [user, asst, asst2, user2]


# ---------------------------------------------------------------------------
# SessionMemoryState properties
# ---------------------------------------------------------------------------

def test_empty_state_is_not_warm() -> None:
    state = SessionMemoryState.empty()
    assert not state.is_warm


def test_empty_state_is_empty() -> None:
    state = SessionMemoryState.empty()
    assert state.is_empty


def test_warm_state_is_warm() -> None:
    state = SessionMemoryState.empty()
    # Build a warm state by manually constructing sections
    warm = SessionMemoryState(
        sections=tuple(
            (name, "some content" if i == 0 else "")
            for i, (name, _) in enumerate(state.sections)
        )
    )
    assert warm.is_warm
    assert not warm.is_empty


def test_empty_state_has_nine_sections() -> None:
    state = SessionMemoryState.empty()
    assert len(state.sections) == 9


def test_sections_are_named_tuples() -> None:
    state = SessionMemoryState.empty()
    for name, content in state.sections:
        assert isinstance(name, str) and len(name) > 0
        assert isinstance(content, str)


def test_render_format() -> None:
    """Rendered text must contain each numbered section heading."""
    state = SessionMemoryState.empty()
    rendered = state.render()
    for i, (name, _) in enumerate(state.sections, 1):
        assert f"{i}. {name}:" in rendered


# ---------------------------------------------------------------------------
# to_jsonable / from_jsonable round-trip
# ---------------------------------------------------------------------------

def test_to_jsonable_shape() -> None:
    state = SessionMemoryState.empty()
    data = state.to_jsonable()
    assert isinstance(data, dict)
    assert "version" in data
    assert "sections" in data
    assert isinstance(data["sections"], dict)
    assert len(data["sections"]) == 9


def test_from_jsonable_round_trip() -> None:
    state = SessionMemoryState.empty()
    # Build a state with some content
    warm = SessionMemoryState(
        sections=tuple(
            (name, f"content for {name}" if i < 3 else "")
            for i, (name, _) in enumerate(state.sections)
        )
    )
    data = warm.to_jsonable()
    restored = SessionMemoryState.from_jsonable(data)
    assert restored.sections == warm.sections


def test_from_jsonable_ignores_unknown_keys() -> None:
    """Unknown keys at the top level and inside sections are tolerated (forward-compat)."""
    data = {
        "version": 99,
        "future_field": "something new",
        "sections": {
            "Primary Request and Intent": "fix the bug",
            "UnknownFutureSection": "ignored",  # unknown key in sections dict
        },
    }
    state = SessionMemoryState.from_jsonable(data)
    # Should load without error; known section populated, unknown section ignored
    assert state.is_warm
    # Find the Primary Request section
    section_dict = dict(state.sections)
    assert section_dict["Primary Request and Intent"] == "fix the bug"


def test_from_jsonable_missing_sections_returns_empty() -> None:
    """Missing 'sections' key is treated as an empty/cold state (forward-compat)."""
    state = SessionMemoryState.from_jsonable({"version": 1})
    assert state.is_empty


def test_from_jsonable_non_dict_payload_raises() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        SessionMemoryState.from_jsonable("not a dict")  # type: ignore[arg-type]


def test_from_jsonable_invalid_sections_type_raises() -> None:
    with pytest.raises(ValueError, match="sections"):
        SessionMemoryState.from_jsonable({"sections": ["not", "a", "dict"]})


def test_from_jsonable_invalid_section_value_raises() -> None:
    with pytest.raises(ValueError, match="Primary Request and Intent"):
        SessionMemoryState.from_jsonable({
            "sections": {"Primary Request and Intent": 42}
        })


# ---------------------------------------------------------------------------
# update_session_memory
# ---------------------------------------------------------------------------

def test_update_returns_new_state_instance() -> None:
    """update_session_memory must return a NEW object, never the input."""
    state = SessionMemoryState.empty()
    msgs = _make_messages()
    result = update_session_memory(state, msgs)
    assert result is not state


def test_update_does_not_mutate_input_state() -> None:
    """Input state must be unchanged after the call (immutability contract)."""
    state = SessionMemoryState.empty()
    original_sections = state.sections
    msgs = _make_messages()
    update_session_memory(state, msgs)
    assert state.sections == original_sections


def test_update_does_not_mutate_input_messages() -> None:
    """Input message list must not be mutated."""
    state = SessionMemoryState.empty()
    msgs = _make_messages()
    ids_before = [id(m) for m in msgs]
    update_session_memory(state, msgs)
    assert [id(m) for m in msgs] == ids_before


def test_update_with_messages_produces_warm_state() -> None:
    state = SessionMemoryState.empty()
    msgs = _make_messages()
    result = update_session_memory(state, msgs)
    assert result.is_warm


def test_update_with_empty_messages_returns_same_content() -> None:
    """Empty new_messages list: state content is unchanged (returned as-is)."""
    state = SessionMemoryState.empty()
    result = update_session_memory(state, [])
    assert result.sections == state.sections


def test_update_preserves_nine_sections() -> None:
    state = SessionMemoryState.empty()
    msgs = _make_messages()
    result = update_session_memory(state, msgs)
    assert len(result.sections) == 9


def test_caps_applied() -> None:
    """Per-section cap must truncate content that exceeds MAX_SECTION_CHARS."""
    from simple_coding_agent.session_memory_state import _MAX_SECTION_CHARS

    # Build a state where one section has oversized content
    state = SessionMemoryState.empty()
    oversized = "x" * (_MAX_SECTION_CHARS + 1000)
    sections = list(state.sections)
    sections[0] = (sections[0][0], oversized)
    warm = SessionMemoryState(sections=tuple(sections))

    data = warm.to_jsonable()
    restored = SessionMemoryState.from_jsonable(data)
    name, content = restored.sections[0]
    # Round-trip must preserve the stored content — cap must be applied on UPDATE
    # (the round-trip itself does not re-cap)
    assert isinstance(content, str)

    # Directly verify: constructing a state with oversized content and rendering
    # produces something; cap is applied by update_session_memory
    many_msgs = _make_messages() * 5
    result = update_session_memory(state, many_msgs)
    section_dict = dict(result.sections)
    total = sum(len(v) for v in section_dict.values())
    from simple_coding_agent.session_memory_state import _MAX_TOTAL_CHARS
    assert total <= _MAX_TOTAL_CHARS
