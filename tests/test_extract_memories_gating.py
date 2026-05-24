"""Tests for the 7-layer gating logic in maybe_extract_memories.

Each test verifies one gate short-circuits extraction when that gate's
condition fires. Cursor tests verify at-least-once semantics.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from simple_coding_agent.extract_memories import ExtractionResult
from simple_coding_agent.extraction_hooks import maybe_extract_memories
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.models import Message, MessageType, Role, ToolCall
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tools import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_uuid() -> str:
    return str(_uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _user_msg(text: str = "hello") -> Message:
    return Message.user(text)


def _assistant_with_write() -> Message:
    return Message(
        uuid=_new_uuid(),
        role=Role.ASSISTANT,
        content=[ToolCall(id="tc_w", name="write_memory_entry", input={})],
        timestamp=_now(),
        type=MessageType.TOOL_USE,
    )


def _base_kwargs(
    tmp_path: Path,
    *,
    messages: list[Message] | None = None,
    is_subloop: bool = False,
    extract_memories_enabled: bool = True,
    auto_memory_enabled: bool = True,
    extraction_in_progress: bool = False,
    last_memory_message_uuid: str | None = None,
    turns_since_last_extraction: int = 1,
    throttle_n: int = 1,
) -> dict:
    """Default kwargs that pass all 7 gates (when runner is mocked to succeed)."""
    msgs = messages if messages is not None else [_user_msg()]
    return dict(
        messages=msgs,
        base_messages_snapshot=[{"role": "user", "content": "hello"}],
        is_subloop=is_subloop,
        extract_memories_enabled=extract_memories_enabled,
        auto_memory_enabled=auto_memory_enabled,
        extraction_in_progress=extraction_in_progress,
        last_memory_message_uuid=last_memory_message_uuid,
        turns_since_last_extraction=turns_since_last_extraction,
        throttle_n=throttle_n,
        provider=MockProvider([MockProvider.direct_answer("ok")]),
        memory_dir=tmp_path,
        system_prompt="extraction sys prompt",
        tool_registry=ToolRegistry(),
        metrics=MetricsCollector(),
    )


_MOCK_SUCCESS = ExtractionResult(written_paths=("p1",), errors=(), turn_count=1)
_EXTRACT_MODULE = "simple_coding_agent.extraction_hooks.ExtractMemoriesRunner"


# ---------------------------------------------------------------------------
# Gate 1: is_subloop
# ---------------------------------------------------------------------------


def test_gate_1_is_subloop_skips(tmp_path):
    """When _is_subloop=True the runner must not be instantiated."""
    kwargs = _base_kwargs(tmp_path, is_subloop=True)
    with patch(_EXTRACT_MODULE) as MockRunner:
        outcome = maybe_extract_memories(**kwargs)
    MockRunner.assert_not_called()
    assert outcome.ran is False
    assert kwargs["metrics"].extract_invocations == 0


# ---------------------------------------------------------------------------
# Gate 2: extract_memories_enabled flag
# ---------------------------------------------------------------------------


def test_gate_2_flag_off_skips(tmp_path):
    """When extract_memories_enabled=False extraction is skipped."""
    kwargs = _base_kwargs(tmp_path, extract_memories_enabled=False)
    with patch(_EXTRACT_MODULE) as MockRunner:
        outcome = maybe_extract_memories(**kwargs)
    MockRunner.assert_not_called()
    assert outcome.ran is False


# ---------------------------------------------------------------------------
# Gate 3: auto_memory_enabled
# ---------------------------------------------------------------------------


def test_gate_3_auto_memory_disabled_skips(tmp_path):
    """When auto_memory_enabled=False (no ProjectMemory wired) skip."""
    kwargs = _base_kwargs(tmp_path, auto_memory_enabled=False)
    with patch(_EXTRACT_MODULE) as MockRunner:
        outcome = maybe_extract_memories(**kwargs)
    MockRunner.assert_not_called()
    assert outcome.ran is False


# ---------------------------------------------------------------------------
# Gate 4: extraction_in_progress
# ---------------------------------------------------------------------------


def test_gate_4_in_progress_skips(tmp_path):
    """Re-entrancy guard: when extraction_in_progress=True skip."""
    kwargs = _base_kwargs(tmp_path, extraction_in_progress=True)
    with patch(_EXTRACT_MODULE) as MockRunner:
        outcome = maybe_extract_memories(**kwargs)
    MockRunner.assert_not_called()
    assert outcome.ran is False


# ---------------------------------------------------------------------------
# Gate 5: hasMemoryWritesSince
# ---------------------------------------------------------------------------


def test_gate_5_has_writes_skips(tmp_path):
    """Agent already wrote a memory this turn — extraction is unnecessary."""
    write_msg = _assistant_with_write()
    # cursor=None means scan from beginning; write_msg is found → skip
    kwargs = _base_kwargs(
        tmp_path,
        messages=[write_msg],
        last_memory_message_uuid=None,
    )
    with patch(_EXTRACT_MODULE) as MockRunner:
        outcome = maybe_extract_memories(**kwargs)
    MockRunner.assert_not_called()
    assert outcome.ran is False


# ---------------------------------------------------------------------------
# Gate 6: throttle
# ---------------------------------------------------------------------------


def test_gate_6_throttle_skips(tmp_path):
    """turns_since_last_extraction < throttle_n → skip."""
    kwargs = _base_kwargs(
        tmp_path,
        turns_since_last_extraction=2,
        throttle_n=5,  # 2 < 5 → skip
    )
    with patch(_EXTRACT_MODULE) as MockRunner:
        outcome = maybe_extract_memories(**kwargs)
    MockRunner.assert_not_called()
    assert outcome.ran is False


# ---------------------------------------------------------------------------
# Gate 7: run — cursor semantics
# ---------------------------------------------------------------------------


def test_cursor_advances_on_success(tmp_path):
    """On successful extraction the cursor advances to the last message uuid."""
    last_msg = _user_msg("final turn input")
    kwargs = _base_kwargs(tmp_path, messages=[last_msg])

    with patch(_EXTRACT_MODULE) as MockRunner:
        MockRunner.return_value.run.return_value = _MOCK_SUCCESS
        outcome = maybe_extract_memories(**kwargs)

    assert outcome.ran is True
    assert outcome.last_memory_message_uuid == last_msg.uuid
    assert outcome.turns_since_last_extraction == 0  # reset on success
    assert kwargs["metrics"].extract_invocations == 1
    assert kwargs["metrics"].extract_writes == 1  # len(written_paths)


def test_cursor_does_not_advance_on_exception(tmp_path):
    """At-least-once: cursor must NOT advance when runner.run() raises."""
    last_msg = _user_msg("input")
    initial_uuid = "fixed-cursor-uuid"
    initial_turns = 7
    kwargs = _base_kwargs(
        tmp_path,
        messages=[last_msg],
        last_memory_message_uuid=initial_uuid,
        turns_since_last_extraction=initial_turns,
    )

    with patch(_EXTRACT_MODULE) as MockRunner:
        MockRunner.return_value.run.side_effect = RuntimeError("provider failed")
        outcome = maybe_extract_memories(**kwargs)

    assert outcome.ran is False
    assert outcome.last_memory_message_uuid == initial_uuid  # not advanced
    assert outcome.turns_since_last_extraction == initial_turns  # not reset
    assert kwargs["metrics"].extract_invocations == 0
