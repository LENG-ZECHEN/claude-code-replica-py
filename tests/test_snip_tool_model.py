"""M4: model-driven snip_history tool tests — written before implementation (TDD).

Covers the pure validation surface (``evaluate_snip_request`` /
``snippable_candidate_uuids``), the registered ``snip_history`` tool's
schema + closure semantics, and the ``SnipNudge`` render contract. All
deterministic: no AgentLoop, no provider, no network.
"""

from __future__ import annotations

from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.snip_tool_model import (
    SnipNudge,
    evaluate_snip_request,
    register_snip_history_tool,
    snippable_candidate_uuids,
)
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _tool_use(uuid: str, tool_use_id: str, name: str = "read_file") -> Message:
    return Message(
        uuid=uuid,
        role=Role.ASSISTANT,
        content=[ToolCall(id=tool_use_id, name=name, input={"path": "f.py"})],
        timestamp="2024-01-01T00:00:00Z",
        type=MessageType.TOOL_USE,
    )


def _tool_result(uuid: str, tool_use_id: str, content: str = "data") -> Message:
    return Message(
        uuid=uuid,
        role=Role.USER,
        content=[ToolResult(tool_use_id=tool_use_id, content=content)],
        timestamp="2024-01-01T00:00:01Z",
        type=MessageType.TOOL_RESULT,
        is_meta=True,
    )


def _user_text(uuid: str, text: str = "do something") -> Message:
    return Message(
        uuid=uuid,
        role=Role.USER,
        content=text,
        timestamp="2024-01-01T00:00:02Z",
        type=MessageType.TEXT,
    )


def _transcript_with_n_results(n: int, *, trailing_user_text: bool = True) -> Transcript:
    """A transcript with n (tool_use, tool_result) pairs and an optional
    trailing user-text message (simulating the current turn)."""
    t = Transcript()
    t.append(_user_text("u-first", "start"))
    for i in range(n):
        t.append(_tool_use(f"a-{i}", f"tc-{i}"))
        t.append(_tool_result(f"r-{i}", f"tc-{i}", content=f"data-{i}"))
    if trailing_user_text:
        t.append(_user_text("u-current", "current turn"))
    return t


# ---------------------------------------------------------------------------
# evaluate_snip_request — happy path
# ---------------------------------------------------------------------------


def test_evaluate_accepts_old_tool_result_uuid() -> None:
    # 8 results; the oldest (r-0) is well outside the recent-5 window.
    t = _transcript_with_n_results(8)
    outcome = evaluate_snip_request(t.all_messages(), ["r-0"])
    assert outcome.refused is False
    assert outcome.removed_uuids == ("r-0",)


def test_evaluate_accepts_multiple_old_uuids() -> None:
    t = _transcript_with_n_results(8)
    outcome = evaluate_snip_request(t.all_messages(), ["r-0", "r-1"])
    assert outcome.refused is False
    assert set(outcome.removed_uuids) == {"r-0", "r-1"}


# ---------------------------------------------------------------------------
# evaluate_snip_request — refusals
# ---------------------------------------------------------------------------


def test_evaluate_refuses_unknown_uuid() -> None:
    t = _transcript_with_n_results(8)
    outcome = evaluate_snip_request(t.all_messages(), ["does-not-exist"])
    assert outcome.refused is True
    assert outcome.reason is not None
    assert "not found" in outcome.reason


def test_evaluate_refuses_non_tool_result_message() -> None:
    # u-first is a plain user-text message, not a tool_result.
    t = _transcript_with_n_results(8)
    outcome = evaluate_snip_request(t.all_messages(), ["u-first"])
    assert outcome.refused is True
    assert outcome.reason is not None
    assert "tool_result" in outcome.reason


def test_evaluate_refuses_recent_within_keep_window() -> None:
    # r-7 is the newest result -> inside the recent-5 protection window.
    t = _transcript_with_n_results(8)
    outcome = evaluate_snip_request(t.all_messages(), ["r-7"])
    assert outcome.refused is True
    assert outcome.reason is not None
    assert "recent" in outcome.reason


def test_evaluate_refuses_future_after_latest_user_text() -> None:
    # No trailing user text -> the latest user-text is "u-first" at index 0,
    # so every result is positionally AFTER it and counts as future.
    t = _transcript_with_n_results(8, trailing_user_text=False)
    outcome = evaluate_snip_request(t.all_messages(), ["r-0"])
    assert outcome.refused is True
    assert outcome.reason is not None
    assert "current turn" in outcome.reason


def test_evaluate_refuses_empty_uuid_list() -> None:
    # An empty message_uuids list must refuse rather than "succeed" with a
    # pointless full-transcript replace_all (no targets == nothing to snip).
    t = _transcript_with_n_results(8)
    outcome = evaluate_snip_request(t.all_messages(), [])
    assert outcome.refused is True
    assert outcome.reason is not None
    assert "no message_uuids" in outcome.reason


# ---------------------------------------------------------------------------
# snippable_candidate_uuids
# ---------------------------------------------------------------------------


def test_candidates_exclude_recent_five() -> None:
    t = _transcript_with_n_results(8)
    candidates = snippable_candidate_uuids(t.all_messages())
    # 8 results, latest 5 protected -> r-0..r-2 are candidates.
    assert candidates == ["r-0", "r-1", "r-2"]


def test_candidates_empty_when_fewer_than_keep_recent() -> None:
    t = _transcript_with_n_results(3)
    assert snippable_candidate_uuids(t.all_messages()) == []


# ---------------------------------------------------------------------------
# register_snip_history_tool — schema + closure semantics
# ---------------------------------------------------------------------------


def test_register_adds_snip_history_with_exact_schema() -> None:
    registry = ToolRegistry()
    register_snip_history_tool(registry, Transcript())
    tool = registry.get("snip_history")
    assert tool.input_schema == {
        "type": "object",
        "properties": {
            "message_uuids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
        },
        "required": ["message_uuids"],
    }


def test_tool_description_documents_wrap_and_rules() -> None:
    registry = ToolRegistry()
    register_snip_history_tool(registry, Transcript())
    desc = registry.get("snip_history").description
    assert len(desc) >= 150
    assert "<msg uuid=" in desc
    assert "tool_result" in desc


def test_tool_removes_messages_from_live_transcript() -> None:
    t = _transcript_with_n_results(8)
    registry = ToolRegistry()
    register_snip_history_tool(registry, t)
    executor = ToolExecutor(registry)

    before = len(t)
    content, is_error = executor.execute("snip_history", {"message_uuids": ["r-0"]})
    assert is_error is False
    assert content == "Snipped 1 messages"
    assert len(t) == before - 1
    assert all(m.uuid != "r-0" for m in t.all_messages())


def test_tool_refusal_surfaces_as_is_error() -> None:
    t = _transcript_with_n_results(8)
    registry = ToolRegistry()
    register_snip_history_tool(registry, t)
    executor = ToolExecutor(registry)

    before = len(t)
    content, is_error = executor.execute("snip_history", {"message_uuids": ["r-7"]})
    assert is_error is True
    assert content.startswith("snip refused:")
    # Transcript untouched on refusal.
    assert len(t) == before


def test_tool_refuses_empty_list_as_is_error() -> None:
    t = _transcript_with_n_results(8)
    registry = ToolRegistry()
    register_snip_history_tool(registry, t)
    executor = ToolExecutor(registry)

    before = len(t)
    content, is_error = executor.execute("snip_history", {"message_uuids": []})
    assert is_error is True
    assert content.startswith("snip refused:")
    assert "no message_uuids" in content
    # Empty list must not trigger a no-op replace_all.
    assert len(t) == before


def test_tool_closure_tracks_replace_all_mutation() -> None:
    # Confirms the closure reads the LIVE transcript, not a snapshot taken at
    # registration time: mutate after register, then snip.
    t = Transcript()
    registry = ToolRegistry()
    register_snip_history_tool(registry, t)
    # Populate AFTER registration.
    t.replace_all(_transcript_with_n_results(8).all_messages())
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("snip_history", {"message_uuids": ["r-0"]})
    assert is_error is False
    assert content == "Snipped 1 messages"


def test_evaluate_does_not_mutate_input() -> None:
    t = _transcript_with_n_results(8)
    messages = t.all_messages()
    snapshot = list(messages)
    evaluate_snip_request(messages, ["r-0"])
    assert messages == snapshot


# ---------------------------------------------------------------------------
# SnipNudge
# ---------------------------------------------------------------------------


def test_snip_nudge_is_frozen() -> None:
    import dataclasses

    nudge = SnipNudge(candidate_uuids=("r-0", "r-1"))
    assert dataclasses.is_dataclass(nudge)
    try:
        nudge.candidate_uuids = ()  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - frozen guarantees this branch is unused
        raise AssertionError("SnipNudge must be frozen")


def test_snip_nudge_render_lists_candidate_uuids() -> None:
    nudge = SnipNudge(candidate_uuids=("r-0", "r-1"))
    body = nudge.render()
    assert "snip_history" in body
    assert "r-0" in body
    assert "r-1" in body
