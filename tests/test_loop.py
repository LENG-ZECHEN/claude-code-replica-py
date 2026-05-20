"""Phase 7 / Step 3: AgentLoop tests — written before implementation (TDD).

Coverage matches the 12 cases enumerated in the Phase 7 instructions:
  1.  direct answer without tools
  2.  single tool call then final answer
  3.  multiple tool calls
  4.  unknown tool handling
  5.  tool exception handling
  6.  max_steps protection
  7.  memory snippets injected into ContextBuilder
  8.  compaction triggered when over budget
  9.  transcript updated after each step
  10. final structured result contains answer, steps, and status
  11. malformed provider response handled clearly
  12. provider call history records built context
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from simple_coding_agent.compact import (
    CLEARED_TOOL_RESULT_CONTENT,
    ContextCompactor,
    MicroCompactor,
)
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopResult, LoopStatus
from simple_coding_agent.memory import MemoryEntry, MemoryType, ProjectMemory, SessionMemory
from simple_coding_agent.models import Message, MessageType, Role, ToolCall, ToolResult
from simple_coding_agent.provider import (
    MockProvider,
    PromptTooLongError,
    ProviderCall,
    ProviderResponse,
    ProviderStreamEvent,
    TokenUsage,
)
from simple_coding_agent.tools import Tool, ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_loop(
    provider: MockProvider,
    tools: list[Tool] | None = None,
    *,
    max_steps: int = 10,
    budget: ContextBudget | None = None,
    session_memory: SessionMemory | None = None,
    project_memory: ProjectMemory | None = None,
    compactor: ContextCompactor | None = None,
    microcompactor: MicroCompactor | None = None,
    transcript: Transcript | None = None,
    system_prompt: str = "You are a coding assistant.",
) -> tuple[AgentLoop, Transcript, ToolRegistry]:
    registry = ToolRegistry()
    for t in tools or []:
        registry.register(t)
    executor = ToolExecutor(registry)
    real_budget = budget or ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    real_transcript = transcript or Transcript()
    context_builder = ContextBuilder(budget=real_budget)
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=real_transcript,
        context_builder=context_builder,
        budget=real_budget,
        registry=registry,
        compactor=compactor,
        microcompactor=microcompactor,
        session_memory=session_memory,
        project_memory=project_memory,
        system_prompt=system_prompt,
        max_steps=max_steps,
    )
    return loop, real_transcript, registry


class _PromptTooLongThenProvider:
    def __init__(self, script: list[PromptTooLongError | ProviderResponse]) -> None:
        self._script = list(script)
        self._index = 0
        self.history: list[ProviderCall] = []

    def call(
        self,
        system: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> ProviderResponse:
        item = self._script[self._index]
        self._index += 1
        if isinstance(item, PromptTooLongError):
            raise item
        self.history.append(ProviderCall(
            system=system,
            messages=list(messages),
            tools=list(tools),
            response=item,
        ))
        return item

    def stream_call(
        self,
        system: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> Iterator[ProviderStreamEvent]:
        response = self.call(system=system, messages=messages, tools=tools)
        if response.text:
            yield ProviderStreamEvent.text_delta(response.text)
        yield ProviderStreamEvent.done(response)


class _CountingCompactor(ContextCompactor):
    def __init__(self) -> None:
        super().__init__(keep_recent=1, compact_threshold=1.0)
        self.compact_calls = 0

    def should_compact(self, transcript: Transcript, budget: ContextBudget) -> bool:
        return False

    def compact(self, transcript: Transcript, budget: ContextBudget):
        self.compact_calls += 1
        return super().compact(transcript, budget)


class _RecordingProjectMemory:
    def __init__(self) -> None:
        self.queries: list[str | None] = []

    def to_snippets(self, query: str | None = None) -> list[str]:
        self.queries.append(query)
        return ["[project] recorded: query captured"]


class _AlwaysMicroCompactor(MicroCompactor):
    def __init__(self) -> None:
        self.microcompact_calls = 0

    def should_microcompact(
        self,
        messages: list[Message],
        threshold_minutes: int = 60,
        now: datetime | None = None,
    ) -> bool:
        return True

    def microcompact(self, messages: list[Message]) -> list[Message]:
        self.microcompact_calls += 1
        return super().microcompact(messages)


def _tool_exchange_messages(
    tool_use_id: str = "tc_old",
    tool_name: str = "read_file",
    result_content: str = "old tool result body",
    timestamp: str = "2024-01-01T00:00:00+00:00",
) -> list[Message]:
    return [
        Message(
            uuid=f"asst-{tool_use_id}",
            role=Role.ASSISTANT,
            content=[ToolCall(id=tool_use_id, name=tool_name, input={"path": "x.py"})],
            timestamp=timestamp,
            type=MessageType.TOOL_USE,
        ),
        Message(
            uuid=f"user-{tool_use_id}",
            role=Role.USER,
            content=[ToolResult(tool_use_id=tool_use_id, content=result_content)],
            timestamp=timestamp,
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        ),
    ]


# ---------------------------------------------------------------------------
# 1. Direct answer without tools
# ---------------------------------------------------------------------------

def test_direct_answer_returns_final_text() -> None:
    p = MockProvider([MockProvider.direct_answer("hello, world")])
    loop, _, _ = _make_loop(p)
    result = loop.run("say hi")
    assert result.answer == "hello, world"
    assert result.status == LoopStatus.COMPLETED


def test_direct_answer_one_step_no_tools() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p)
    result = loop.run("hello")
    assert len(result.steps) == 1
    assert result.steps[0].tool_calls == []
    assert result.steps[0].tool_results == []


def test_direct_answer_appends_assistant_to_transcript() -> None:
    p = MockProvider([MockProvider.direct_answer("done")])
    loop, transcript, _ = _make_loop(p)
    loop.run("hi")
    msgs = transcript.all_messages()
    assert msgs[0].role == Role.USER
    assert msgs[-1].role == Role.ASSISTANT
    assert msgs[-1].content == "done"


def test_run_stream_yields_text_delta_and_done_result() -> None:
    p = MockProvider([MockProvider.direct_answer("streamed answer")])
    loop, transcript, _ = _make_loop(p)

    events = list(loop.run_stream("say hi"))

    assert [(event.type, event.text) for event in events[:-1]] == [
        ("text_delta", "streamed answer")
    ]
    assert events[-1].type == "done"
    assert events[-1].result is not None
    assert events[-1].result.status == LoopStatus.COMPLETED
    assert transcript.all_messages()[-1].content == "streamed answer"


# ---------------------------------------------------------------------------
# 2. Single tool call then final answer
# ---------------------------------------------------------------------------

def test_single_tool_then_final_answer() -> None:
    read_tool = Tool(
        name="read_file",
        description="Read a file",
        input_schema={},
        fn=lambda path: f"contents of {path}",
    )
    p = MockProvider([
        MockProvider.tool_call("read_file", {"path": "x.py"}, id="tu_1"),
        MockProvider.direct_answer("the file says: contents of x.py"),
    ])
    loop, _, _ = _make_loop(p, tools=[read_tool])
    result = loop.run("read x.py")
    assert result.status == LoopStatus.COMPLETED
    assert result.answer == "the file says: contents of x.py"
    assert len(result.steps) == 2


def test_single_tool_step_records_call_and_result() -> None:
    read_tool = Tool(
        name="read_file", description="", input_schema={},
        fn=lambda path: "abc",
    )
    p = MockProvider([
        MockProvider.tool_call("read_file", {"path": "x"}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, _, _ = _make_loop(p, tools=[read_tool])
    result = loop.run("read x")
    assert result.steps[0].tool_calls[0].name == "read_file"
    assert result.steps[0].tool_calls[0].input == {"path": "x"}
    assert result.steps[0].tool_results[0].content == "abc"
    assert result.steps[0].tool_results[0].is_error is False


def test_run_stream_yields_tool_step_between_text_turns() -> None:
    read_tool = Tool(
        name="read_file",
        description="Read a file",
        input_schema={},
        fn=lambda path: f"contents of {path}",
    )
    p = MockProvider([
        MockProvider.tool_call("read_file", {"path": "x.py"}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, _, _ = _make_loop(p, tools=[read_tool])

    events = list(loop.run_stream("read x.py"))

    assert [event.type for event in events] == ["tool_step", "text_delta", "done"]
    assert events[0].tool_call is not None
    assert events[0].tool_call.name == "read_file"
    assert events[0].tool_result is not None
    assert events[0].tool_result.content == "contents of x.py"
    assert events[-1].result is not None
    assert events[-1].result.status == LoopStatus.COMPLETED


# ---------------------------------------------------------------------------
# 3. Multiple tool calls in sequence
# ---------------------------------------------------------------------------

def test_multiple_tool_calls_in_sequence() -> None:
    echo = Tool(
        name="echo", description="", input_schema={},
        fn=lambda text: text,
    )
    p = MockProvider([
        MockProvider.tool_call("echo", {"text": "a"}, id="tu_1"),
        MockProvider.tool_call("echo", {"text": "b"}, id="tu_2"),
        MockProvider.direct_answer("both echoed"),
    ])
    loop, _, _ = _make_loop(p, tools=[echo])
    result = loop.run("echo a and b")
    assert result.status == LoopStatus.COMPLETED
    assert len(result.steps) == 3
    assert result.steps[0].tool_calls[0].input == {"text": "a"}
    assert result.steps[1].tool_calls[0].input == {"text": "b"}
    assert result.steps[0].tool_results[0].content == "a"
    assert result.steps[1].tool_results[0].content == "b"


def test_each_tool_call_is_a_separate_step() -> None:
    t = Tool(name="t", description="", input_schema={}, fn=lambda: "x")
    p = MockProvider([
        MockProvider.tool_call("t", {}, id="tu_1"),
        MockProvider.tool_call("t", {}, id="tu_2"),
        MockProvider.tool_call("t", {}, id="tu_3"),
        MockProvider.direct_answer("end"),
    ])
    loop, _, _ = _make_loop(p, tools=[t])
    result = loop.run("loop x3")
    assert len(result.steps) == 4
    assert result.steps[0].turn == 1
    assert result.steps[3].turn == 4


# ---------------------------------------------------------------------------
# 4. Unknown tool handling
# ---------------------------------------------------------------------------

def test_unknown_tool_returns_error_result_not_raises() -> None:
    p = MockProvider([
        MockProvider.tool_call("does_not_exist", {}, id="tu_1"),
        MockProvider.direct_answer("recovered"),
    ])
    loop, _, _ = _make_loop(p)
    result = loop.run("call missing")
    assert result.status == LoopStatus.COMPLETED
    assert result.steps[0].tool_results[0].is_error is True
    assert "does_not_exist" in result.steps[0].tool_results[0].content


# ---------------------------------------------------------------------------
# 5. Tool exception handling
# ---------------------------------------------------------------------------

def test_tool_exception_is_captured_as_error_result() -> None:
    def fail() -> str:
        raise RuntimeError("boom")
    bad = Tool(name="bad", description="", input_schema={}, fn=fail)
    p = MockProvider([
        MockProvider.tool_call("bad", {}, id="tu_1"),
        MockProvider.direct_answer("recovered from error"),
    ])
    loop, _, _ = _make_loop(p, tools=[bad])
    result = loop.run("try bad tool")
    assert result.status == LoopStatus.COMPLETED
    assert result.steps[0].tool_results[0].is_error is True
    assert "boom" in result.steps[0].tool_results[0].content


def test_tool_exception_still_appended_to_transcript() -> None:
    def fail() -> str:
        raise ValueError("nope")
    bad = Tool(name="bad", description="", input_schema={}, fn=fail)
    p = MockProvider([
        MockProvider.tool_call("bad", {}, id="tu_1"),
        MockProvider.direct_answer("ok"),
    ])
    loop, transcript, _ = _make_loop(p, tools=[bad])
    loop.run("test")
    msgs = transcript.all_messages()
    tool_result_msgs = [m for m in msgs if m.type == MessageType.TOOL_RESULT]
    assert len(tool_result_msgs) == 1
    content = tool_result_msgs[0].content
    assert isinstance(content, list)
    assert isinstance(content[0], ToolResult)
    assert content[0].is_error is True


def test_mixed_text_and_tool_call_preserves_text_in_transcript() -> None:
    read_tool = Tool(
        name="read_file",
        description="Read a file",
        input_schema={},
        fn=lambda path: f"contents of {path}",
    )
    mixed = ProviderResponse(
        text="I will inspect the file first.",
        tool_calls=[ToolCall(id="tu_1", name="read_file", input={"path": "x.py"})],
        usage=TokenUsage(),
        stop_reason="tool_use",
    )
    p = MockProvider([
        mixed,
        MockProvider.direct_answer("done"),
    ])
    loop, transcript, _ = _make_loop(p, tools=[read_tool])

    result = loop.run("read x.py")

    assert result.status == LoopStatus.COMPLETED
    msgs = transcript.all_messages()
    assert msgs[1].role == Role.ASSISTANT
    assert msgs[1].content == "I will inspect the file first."
    assert msgs[2].type == MessageType.TOOL_USE


# ---------------------------------------------------------------------------
# 6. max_steps protection
# ---------------------------------------------------------------------------

def test_max_steps_status_when_provider_keeps_calling_tools() -> None:
    t = Tool(name="loop_tool", description="", input_schema={}, fn=lambda: "x")
    script = [MockProvider.tool_call("loop_tool", {}, id=f"tu_{i}") for i in range(15)]
    p = MockProvider(script)
    loop, _, _ = _make_loop(p, tools=[t], max_steps=5)
    result = loop.run("loop forever")
    assert result.status == LoopStatus.MAX_STEPS
    assert len(result.steps) == 5


def test_max_steps_one_still_records_a_step() -> None:
    """max_steps=1 should produce one step then stop."""
    t = Tool(name="loop_tool", description="", input_schema={}, fn=lambda: "x")
    script = [MockProvider.tool_call("loop_tool", {}, id=f"tu_{i}") for i in range(3)]
    p = MockProvider(script)
    loop, _, _ = _make_loop(p, tools=[t], max_steps=1)
    result = loop.run("loop")
    assert result.status == LoopStatus.MAX_STEPS
    assert len(result.steps) == 1


# ---------------------------------------------------------------------------
# 7. Memory snippets injected into ContextBuilder
# ---------------------------------------------------------------------------

def test_session_memory_appears_in_provider_system_prompt() -> None:
    session = SessionMemory()
    session.add(MemoryEntry(
        name="pref-style",
        body="Prefer terse output.",
        type=MemoryType.FEEDBACK,
    ))
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, session_memory=session)
    loop.run("hi")
    assert "Prefer terse output." in p.history[0].system


def test_memory_snippets_recorded_in_step() -> None:
    session = SessionMemory()
    session.add(MemoryEntry(
        name="x",
        body="some project fact",
        type=MemoryType.PROJECT,
    ))
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, session_memory=session)
    result = loop.run("hi")
    assert any("some project fact" in s for s in result.steps[0].memory_injected)


def test_no_memory_injected_when_no_memory_store() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p)
    result = loop.run("hi")
    assert result.steps[0].memory_injected == []


def test_project_memory_receives_latest_user_text_as_query() -> None:
    project_memory = _RecordingProjectMemory()
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, project_memory=project_memory)

    result = loop.run("Need pytest guidance for the backend")

    assert project_memory.queries == ["Need pytest guidance for the backend"]
    assert result.steps[0].memory_injected == ["[project] recorded: query captured"]


# ---------------------------------------------------------------------------
# 8. Compaction triggered when over budget
# ---------------------------------------------------------------------------

def test_compaction_triggered_when_transcript_over_budget() -> None:
    transcript = Transcript()
    for i in range(20):
        transcript.append(Message.user(f"user {i}: " + "x" * 200))
        transcript.append(Message.assistant(f"asst {i}: " + "y" * 200))

    budget = ContextBudget(max_tokens=300, reserved_output_tokens=0)
    compactor = ContextCompactor(keep_recent=2, compact_threshold=0.5)
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(
        p,
        budget=budget,
        transcript=transcript,
        compactor=compactor,
    )
    result = loop.run("trigger compaction")
    assert result.compacted is True


def test_compaction_step_flag_set_when_compacted() -> None:
    transcript = Transcript()
    for i in range(10):
        transcript.append(Message.user("u" + "x" * 100))
        transcript.append(Message.assistant("a" + "y" * 100))
    budget = ContextBudget(max_tokens=200, reserved_output_tokens=0)
    compactor = ContextCompactor(keep_recent=2, compact_threshold=0.5)
    p = MockProvider([MockProvider.direct_answer("done")])
    loop, _, _ = _make_loop(
        p,
        budget=budget,
        transcript=transcript,
        compactor=compactor,
    )
    result = loop.run("ok")
    assert result.steps[0].compacted is True


def test_no_compaction_when_under_threshold() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    compactor = ContextCompactor(keep_recent=10, compact_threshold=0.9)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    loop, _, _ = _make_loop(p, compactor=compactor, budget=budget)
    result = loop.run("small input")
    assert result.compacted is False


# ---------------------------------------------------------------------------
# 8b. Microcompact old tool results before context building
# ---------------------------------------------------------------------------

def test_agent_loop_microcompacts_old_tool_results_before_context_building() -> None:
    now = datetime.now(UTC)
    old_timestamp = (now - timedelta(minutes=90)).isoformat()
    transcript = Transcript()
    for msg in _tool_exchange_messages(timestamp=old_timestamp):
        transcript.append(msg)
    transcript.append(Message(
        uuid="old-final",
        role=Role.ASSISTANT,
        content="old final answer",
        timestamp=old_timestamp,
    ))
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, transcript=transcript)

    result = loop.run("continue")

    assert result.status == LoopStatus.COMPLETED
    sent_context = str(p.history[0].messages)
    assert CLEARED_TOOL_RESULT_CONTENT in sent_context
    assert "old tool result body" not in sent_context


def test_agent_loop_does_not_microcompact_recent_tool_results() -> None:
    recent_timestamp = datetime.now(UTC).isoformat()
    transcript = Transcript()
    for msg in _tool_exchange_messages(timestamp=recent_timestamp):
        transcript.append(msg)
    transcript.append(Message(
        uuid="recent-final",
        role=Role.ASSISTANT,
        content="recent final answer",
        timestamp=recent_timestamp,
    ))
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, transcript=transcript)

    result = loop.run("continue")

    assert result.status == LoopStatus.COMPLETED
    sent_context = str(p.history[0].messages)
    assert "old tool result body" in sent_context
    assert CLEARED_TOOL_RESULT_CONTENT not in sent_context


def test_agent_loop_microcompacts_at_most_once_per_session() -> None:
    transcript = Transcript()
    for msg in _tool_exchange_messages():
        transcript.append(msg)
    microcompactor = _AlwaysMicroCompactor()
    echo = Tool(name="echo", description="", input_schema={}, fn=lambda text: text)
    p = MockProvider([
        MockProvider.tool_call("echo", {"text": "first"}, id="tu_echo"),
        MockProvider.direct_answer("done"),
    ])
    loop, _, _ = _make_loop(
        p,
        tools=[echo],
        transcript=transcript,
        microcompactor=microcompactor,
    )

    result = loop.run("call echo")

    assert result.status == LoopStatus.COMPLETED
    assert microcompactor.microcompact_calls == 1


# ---------------------------------------------------------------------------
# 9. Transcript updated after each step
# ---------------------------------------------------------------------------

def test_transcript_has_user_and_assistant_after_direct_answer() -> None:
    p = MockProvider([MockProvider.direct_answer("hi")])
    loop, transcript, _ = _make_loop(p)
    assert len(transcript) == 0
    loop.run("hello")
    assert len(transcript) == 2
    msgs = transcript.all_messages()
    assert msgs[0].role == Role.USER
    assert msgs[1].role == Role.ASSISTANT


def test_transcript_includes_tool_use_and_tool_result_messages() -> None:
    t = Tool(name="t", description="", input_schema={}, fn=lambda: "result")
    p = MockProvider([
        MockProvider.tool_call("t", {}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, transcript, _ = _make_loop(p, tools=[t])
    loop.run("call t")
    msgs = transcript.all_messages()
    assert len(msgs) == 4
    assert msgs[0].role == Role.USER
    assert msgs[1].type == MessageType.TOOL_USE
    assert msgs[2].type == MessageType.TOOL_RESULT
    assert msgs[3].role == Role.ASSISTANT
    assert msgs[3].content == "done"


def test_transcript_tool_use_message_contains_tool_call() -> None:
    t = Tool(name="t", description="", input_schema={}, fn=lambda: "r")
    p = MockProvider([
        MockProvider.tool_call("t", {"k": "v"}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, transcript, _ = _make_loop(p, tools=[t])
    loop.run("test")
    msgs = transcript.all_messages()
    tool_use_msg = msgs[1]
    assert isinstance(tool_use_msg.content, list)
    assert isinstance(tool_use_msg.content[0], ToolCall)
    assert tool_use_msg.content[0].name == "t"
    assert tool_use_msg.content[0].input == {"k": "v"}


# ---------------------------------------------------------------------------
# 10. Final structured result contains answer, steps, status
# ---------------------------------------------------------------------------

def test_loop_result_shape() -> None:
    p = MockProvider([MockProvider.direct_answer("answer")])
    loop, _, _ = _make_loop(p)
    result = loop.run("hi")
    assert isinstance(result, LoopResult)
    assert hasattr(result, "answer")
    assert hasattr(result, "steps")
    assert hasattr(result, "status")
    assert hasattr(result, "compacted")


def test_loop_result_status_values() -> None:
    """status uses the LoopStatus enum, not a free-form string."""
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p)
    r = loop.run("x")
    assert r.status in (
        LoopStatus.COMPLETED,
        LoopStatus.MAX_STEPS,
        LoopStatus.MAX_TOKENS,
        LoopStatus.MALFORMED,
    )


def test_max_tokens_response_returns_partial_answer_not_completed() -> None:
    p = MockProvider([
        ProviderResponse(
            text="partial answer",
            tool_calls=[],
            usage=TokenUsage(),
            stop_reason="max_tokens",
        )
    ])
    loop, transcript, _ = _make_loop(p)

    result = loop.run("answer fully")

    assert result.status == LoopStatus.MAX_TOKENS
    assert result.answer == "partial answer"
    assert len(result.steps) == 1
    assert transcript.all_messages()[-1].content == "partial answer"


def test_run_stream_max_tokens_preserves_partial_answer() -> None:
    p = MockProvider([
        ProviderResponse(
            text="partial answer",
            tool_calls=[],
            usage=TokenUsage(),
            stop_reason="max_tokens",
        )
    ])
    loop, _, _ = _make_loop(p)

    events = list(loop.run_stream("answer fully"))

    assert [event.text for event in events if event.type == "text_delta"] == ["partial answer"]
    assert events[-1].result is not None
    assert events[-1].result.status == LoopStatus.MAX_TOKENS
    assert events[-1].result.answer == "partial answer"


# ---------------------------------------------------------------------------
# 10b. Reactive compact on prompt-too-long provider errors
# ---------------------------------------------------------------------------

def test_run_reactive_compact_retries_after_prompt_too_long() -> None:
    provider = _PromptTooLongThenProvider([
        PromptTooLongError("prompt too long"),
        MockProvider.direct_answer("recovered"),
    ])
    compactor = _CountingCompactor()
    loop, _, _ = _make_loop(provider, compactor=compactor)

    result = loop.run("large request")

    assert result.status == LoopStatus.COMPLETED
    assert result.answer == "recovered"
    assert result.compacted is True
    assert compactor.compact_calls == 1
    assert len(provider.history) == 1


def test_run_reactive_compact_retries_only_once() -> None:
    provider = _PromptTooLongThenProvider([
        PromptTooLongError("prompt too long"),
        PromptTooLongError("still too long"),
    ])
    compactor = _CountingCompactor()
    loop, _, _ = _make_loop(provider, compactor=compactor)

    result = loop.run("large request")

    assert result.status == LoopStatus.MAX_TOKENS
    assert result.answer is None
    assert result.compacted is True
    assert compactor.compact_calls == 1
    assert len(provider.history) == 0


def test_run_stream_reactive_compact_retries_after_prompt_too_long() -> None:
    provider = _PromptTooLongThenProvider([
        PromptTooLongError("prompt too long"),
        MockProvider.direct_answer("stream recovered"),
    ])
    compactor = _CountingCompactor()
    loop, _, _ = _make_loop(provider, compactor=compactor)

    events = list(loop.run_stream("large request"))

    assert [event.text for event in events if event.type == "text_delta"] == [
        "stream recovered"
    ]
    assert events[-1].result is not None
    assert events[-1].result.status == LoopStatus.COMPLETED
    assert events[-1].result.compacted is True
    assert compactor.compact_calls == 1
    assert len(provider.history) == 1


def test_run_stream_reactive_compact_retries_only_once() -> None:
    provider = _PromptTooLongThenProvider([
        PromptTooLongError("prompt too long"),
        PromptTooLongError("still too long"),
    ])
    compactor = _CountingCompactor()
    loop, _, _ = _make_loop(provider, compactor=compactor)

    events = list(loop.run_stream("large request"))

    assert events[-1].type == "done"
    assert events[-1].result is not None
    assert events[-1].result.status == LoopStatus.MAX_TOKENS
    assert events[-1].result.compacted is True
    assert compactor.compact_calls == 1
    assert len(provider.history) == 0


# ---------------------------------------------------------------------------
# 11. Malformed provider response
# ---------------------------------------------------------------------------

def test_malformed_response_returns_malformed_status() -> None:
    p = MockProvider([MockProvider.malformed()])
    loop, _, _ = _make_loop(p)
    result = loop.run("test")
    assert result.status == LoopStatus.MALFORMED
    assert result.answer is None


def test_malformed_response_does_not_raise() -> None:
    p = MockProvider([MockProvider.malformed()])
    loop, _, _ = _make_loop(p)
    result = loop.run("test")
    assert result is not None


# ---------------------------------------------------------------------------
# 12. Provider call history records built context
# ---------------------------------------------------------------------------

def test_provider_history_records_system_prompt() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, system_prompt="You are a code assistant.")
    loop.run("test")
    assert "You are a code assistant." in p.history[0].system


def test_provider_history_records_user_message() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p)
    loop.run("hello world")
    found = False
    for m in p.history[0].messages:
        content = m.get("content")
        if isinstance(content, str) and "hello world" in content:
            found = True
            break
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "hello world" in str(block):
                    found = True
                    break
    assert found, f"User message not found in: {p.history[0].messages}"


def test_provider_history_records_tools_for_each_call() -> None:
    t = Tool(
        name="echo", description="echo", input_schema={"type": "object"},
        fn=lambda text: text,
    )
    p = MockProvider([
        MockProvider.tool_call("echo", {"text": "hi"}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, _, _ = _make_loop(p, tools=[t])
    loop.run("test")
    assert len(p.history) == 2
    for entry in p.history:
        names: list[str] = [tool["name"] for tool in entry.tools]
        assert "echo" in names


def test_provider_history_grows_with_each_step() -> None:
    t = Tool(name="t", description="", input_schema={}, fn=lambda: "r")
    p = MockProvider([
        MockProvider.tool_call("t", {}, id="tu_1"),
        MockProvider.tool_call("t", {}, id="tu_2"),
        MockProvider.direct_answer("end"),
    ])
    loop, _, _ = _make_loop(p, tools=[t])
    loop.run("test")
    assert len(p.history) == 3
