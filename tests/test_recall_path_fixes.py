"""Regression tests for the auto-memory-overhaul recall-path fixes.

Covers review findings:
  #1 — recent_tools must reach the selector (was always [] in the live loop
       because injection runs AFTER the current user message is appended).
  #4 — find_relevant_memories returns a RecallResult so the memory_select trace
       reports the REAL fallback_used flag and the scanned manifest_size
       (previously hardcoded False / mislabelled as the selected count).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from simple_coding_agent.memdir import RecallResult, find_relevant_memories
from simple_coding_agent.models import Message, MessageType, Role, ToolCall, ToolResult
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.recall_hooks import inject_memory_attachments
from simple_coding_agent.transcript import Transcript


def _write_memory(directory: Path, entry_id: str, name: str, desc: str) -> None:
    path = directory / f"{entry_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ntype: user\ndescription: {desc}\n"
        f"created_at: 2026-01-01T00:00:00+00:00\n---\n\nBody text.\n",
        encoding="utf-8",
    )


class _RecordingSelector:
    """Selector stub: records the `user` payload, returns fixed filenames."""

    def __init__(self, filenames: list[str]) -> None:
        self._filenames = filenames
        self.last_user: str | None = None

    def call_selector(
        self,
        *,
        system: str,
        user: str,
        output_schema: dict[str, Any],
        max_tokens: int = 256,
    ) -> dict[str, Any]:
        self.last_user = user
        return {"filenames": self._filenames}


class _RecordingTracer:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def emit(self, channel: str, /, **fields: Any) -> None:
        self.events.append((channel, fields))


# --- Finding #1: recent_tools reaches the selector --------------------------


def test_recent_tools_excludes_current_user_turn(tmp_path: Path) -> None:
    """inject runs after the new user msg is appended; recent_tools must still
    reflect the PREVIOUS assistant turn's successful tools, not be empty."""
    _write_memory(tmp_path, "user/role", "Role", "coding style preferences guide")
    transcript = Transcript()
    transcript.append(
        Message(
            uuid="a1",
            role=Role.ASSISTANT,
            content=[ToolCall(id="tc1", name="read_file", input={})],
            timestamp="2026-01-01T00:00:00",
            type=MessageType.TOOL_USE,
        )
    )
    transcript.append(
        Message(
            uuid="r1",
            role=Role.USER,
            content=[ToolResult(tool_use_id="tc1", content="ok", is_error=False)],
            timestamp="2026-01-01T00:00:00",
            type=MessageType.TOOL_RESULT,
        )
    )
    # Current turn's user input — appended by the loop before injection runs.
    transcript.append(Message.user("what is my coding style preference"))

    selector = _RecordingSelector(["user/role.md"])
    inject_memory_attachments(
        transcript,
        "what is my coding style preference",
        selector,
        tmp_path,
        True,
        set(),
        0,
        _RecordingTracer(),
    )
    assert selector.last_user is not None
    assert "Recently-used tools" in selector.last_user
    assert "read_file" in selector.last_user


# --- Finding #4: RecallResult + accurate memory_select trace ----------------


def test_find_relevant_memories_returns_recall_result(tmp_path: Path) -> None:
    _write_memory(tmp_path, "user/role", "Role", "coding role")
    provider = MockProvider([], selector_responses=[{"filenames": ["user/role.md"]}])
    result = find_relevant_memories(
        "what is my role",
        tmp_path,
        provider,
        already_surfaced=set(),
        recent_tools=[],
        session_bytes_used=0,
    )
    assert isinstance(result, RecallResult)
    assert result.fallback_used is False
    assert result.manifest_size == 1
    assert [h.id for h in result.headers] == ["user/role"]


def test_recall_result_fallback_used_on_selector_error(tmp_path: Path) -> None:
    _write_memory(tmp_path, "user/role", "Role", "coding preferences style guide")
    provider = MockProvider([], selector_responses=[])  # SelectorError on call
    result = find_relevant_memories(
        "coding preferences style guide here",
        tmp_path,
        provider,
        already_surfaced=set(),
        recent_tools=[],
        session_bytes_used=0,
    )
    assert result.fallback_used is True
    assert result.manifest_size == 1
    assert len(result.headers) >= 1


def test_trace_reports_real_fallback_used(tmp_path: Path) -> None:
    _write_memory(tmp_path, "user/role", "Role", "coding preferences style guide")
    provider = MockProvider([], selector_responses=[])  # error -> Jaccard fallback
    transcript = Transcript()
    transcript.append(Message.user("coding preferences style guide here"))
    tracer = _RecordingTracer()
    inject_memory_attachments(
        transcript,
        "coding preferences style guide here",
        provider,
        tmp_path,
        True,
        set(),
        0,
        tracer,
    )
    select = [fields for channel, fields in tracer.events if channel == "memory_select"]
    assert select, "no memory_select trace emitted"
    assert select[-1]["fallback_used"] is True
    assert select[-1]["manifest_size"] == 1
