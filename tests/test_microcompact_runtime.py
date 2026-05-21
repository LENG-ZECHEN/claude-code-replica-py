"""Phase C2: runtime tests for MicroCompactor wired into AgentLoop.

The unit-level test_compact.py exercises MicroCompactor.microcompact() in
isolation. These tests verify the *runtime* path through AgentLoop._maybe_
microcompact(): an aged assistant message must clear compactable tool
results before context assembly; the cleanup must run at most once per
loop instance; and a recent transcript must leave tool results untouched.

Test plan: RUNTIME_ACTIVATION_PLAN.md section 3.3.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from simple_coding_agent.compact import (
    CLEARED_TOOL_RESULT_CONTENT,
    MicroCompactor,
)
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tools import Tool, ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_loop(
    provider: MockProvider,
    *,
    tools: list[Tool] | None = None,
    transcript: Transcript | None = None,
    microcompactor: MicroCompactor | None = None,
) -> tuple[AgentLoop, Transcript]:
    registry = ToolRegistry()
    for tool in tools or []:
        registry.register(tool)
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    real_transcript = transcript or Transcript()
    builder = ContextBuilder(budget=budget)
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=real_transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        microcompactor=microcompactor,
        max_steps=5,
    )
    return loop, real_transcript


def _aged_tool_exchange(timestamp: str) -> list[Message]:
    """A read_file call + result + final assistant text, all at `timestamp`."""
    return [
        Message(
            uuid="asst-old-call",
            role=Role.ASSISTANT,
            content=[ToolCall(
                id="tu_old",
                name="read_file",
                input={"path": "old.py"},
            )],
            timestamp=timestamp,
            type=MessageType.TOOL_USE,
        ),
        Message(
            uuid="user-old-result",
            role=Role.USER,
            content=[ToolResult(
                tool_use_id="tu_old",
                content="aged tool result body",
            )],
            timestamp=timestamp,
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        ),
        Message(
            uuid="asst-old-final",
            role=Role.ASSISTANT,
            content="aged final answer",
            timestamp=timestamp,
        ),
    ]


class _CallCountingMicroCompactor(MicroCompactor):
    """Wraps MicroCompactor to count microcompact() invocations."""

    def __init__(self) -> None:
        self.microcompact_calls = 0

    def microcompact(self, messages: list[Message]) -> list[Message]:
        self.microcompact_calls += 1
        return super().microcompact(messages)


# ---------------------------------------------------------------------------
# 1. Fires when last assistant message is older than 60 minutes
# ---------------------------------------------------------------------------

def test_microcompact_fires_when_assistant_older_than_60min(
    monkeypatch: Any,
) -> None:
    real_now = datetime.now(UTC)
    aged_ts = (real_now - timedelta(minutes=61)).isoformat()
    transcript = Transcript()
    for msg in _aged_tool_exchange(aged_ts):
        transcript.append(msg)

    # Lock `datetime.now()` inside the compact module so the loop reads the
    # aged stamp as > 60 min in the past regardless of when the test runs.
    fixed_now = real_now

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(
        "simple_coding_agent.compact.datetime",
        _FixedDatetime,
    )

    provider = MockProvider([MockProvider.direct_answer("next answer")])
    loop, _ = _build_loop(provider, transcript=transcript)

    loop.run("continue")

    sent = str(provider.history[0].messages)
    assert CLEARED_TOOL_RESULT_CONTENT in sent
    assert "aged tool result body" not in sent


# ---------------------------------------------------------------------------
# 2. Runs at most once per loop instance even across multiple run() calls
# ---------------------------------------------------------------------------

def test_microcompact_runs_at_most_once_per_loop_instance() -> None:
    aged_ts = (datetime.now(UTC) - timedelta(minutes=120)).isoformat()
    transcript = Transcript()
    for msg in _aged_tool_exchange(aged_ts):
        transcript.append(msg)

    counter = _CallCountingMicroCompactor()
    provider = MockProvider([
        MockProvider.direct_answer("first"),
        MockProvider.direct_answer("second"),
    ])
    loop, _ = _build_loop(
        provider, transcript=transcript, microcompactor=counter,
    )

    loop.run("first request")
    loop.run("second request")

    assert counter.microcompact_calls == 1
    assert loop._microcompacted is True


# ---------------------------------------------------------------------------
# 3. Skipped entirely when the most recent assistant is still fresh
# ---------------------------------------------------------------------------

def test_microcompact_skipped_when_no_old_assistant() -> None:
    fresh_ts = datetime.now(UTC).isoformat()
    transcript = Transcript()
    for msg in _aged_tool_exchange(fresh_ts):
        transcript.append(msg)

    counter = _CallCountingMicroCompactor()
    provider = MockProvider([MockProvider.direct_answer("answer")])
    loop, _ = _build_loop(
        provider, transcript=transcript, microcompactor=counter,
    )

    loop.run("continue")

    sent = str(provider.history[0].messages)
    assert "aged tool result body" in sent
    assert CLEARED_TOOL_RESULT_CONTENT not in sent
    assert counter.microcompact_calls == 0
