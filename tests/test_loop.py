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
from simple_coding_agent.snip import SNIPPED_CONTENT, SnipTool
from simple_coding_agent.snip_tool_model import (
    register_snip_history_tool,
    snippable_candidate_uuids,
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
    snip_tool: SnipTool | None = None,
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
        snip_tool=snip_tool,
        session_memory=session_memory,
        project_memory=project_memory,
        system_prompt=system_prompt,
        max_steps=max_steps,
    )
    return loop, real_transcript, registry


def _read_file_tool(content: str = "FILE BODY", *, name: str = "read_file") -> Tool:
    return Tool(
        name=name,
        description="read a file",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        fn=lambda path: content,
    )


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

    def compact(self, transcript: Transcript, budget: ContextBudget, **kwargs):
        self.compact_calls += 1
        return super().compact(transcript, budget, **kwargs)


class _RecordingProjectMemory:
    def __init__(self) -> None:
        self.queries: list[str | None] = []

    def to_snippets(self, query: str | None = None) -> list[str]:
        self.queries.append(query)
        return ["[project] recorded: query captured"]


class _AlwaysMicroCompactor(MicroCompactor):
    def __init__(self) -> None:
        super().__init__()
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


class _OrderingMicroCompactor(MicroCompactor):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def should_microcompact(
        self,
        messages: list[Message],
        threshold_minutes: int = 60,
        now: datetime | None = None,
    ) -> bool:
        self.events.append("micro_should")
        return True

    def microcompact(self, messages: list[Message]) -> list[Message]:
        self.events.append("micro_apply")
        return list(messages)


class _OrderingSnipTool(SnipTool):
    def __init__(self, events: list[str], should: bool = True) -> None:
        self.events = events
        self.should_calls = 0
        self.snip_calls = 0
        self.should = should

    def should_snip(self, messages: list[Message]) -> bool:
        self.should_calls += 1
        self.events.append("snip_should")
        return self.should

    def snip(self, messages: list[Message]) -> list[Message]:
        self.snip_calls += 1
        self.events.append("snip_apply")
        return list(messages)


class _OrderingCompactor(ContextCompactor):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def should_compact(self, transcript: Transcript, budget: ContextBudget) -> bool:
        self.events.append("compact_should")
        return False


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
    # keep_recent=0: clear the single aged result. The MicroCompactor default
    # is now keep_recent=5 (PDF alignment), which would preserve a lone result;
    # this runtime check asserts the pre-PDF clear behaviour explicitly.
    loop, _, _ = _make_loop(
        p, transcript=transcript, microcompactor=MicroCompactor(keep_recent=0),
    )

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


def test_agent_loop_microcompacts_at_most_once_per_assistant_uuid() -> None:
    """Patch 3 (C2): microcompact fires at most once per assistant uuid.

    Under the old "bool flag" design, microcompact fired at most once per
    AgentLoop instance for its entire lifetime. The new design tracks the
    uuid of the latest assistant message at microcompact time so a long
    REPL can re-clear newly aged tool results — but it must still not
    spam every loop iteration. This test confirms that within the
    same turn (single ``run()`` call) microcompact only fires once per
    *new* assistant message: one initial fire against the seed transcript,
    and exactly one re-fire after the provider's tool_call adds a new
    assistant message. After the direct-answer turn appends another
    assistant message, no additional microcompact runs because
    ``_maybe_microcompact`` is only called at the top of each turn,
    not after each appended message.
    """
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
    # Two turns through the loop: the seed transcript's assistant uuid
    # triggers the first fire; the tool_call response appends a new
    # assistant message whose uuid differs from the recorded one, so
    # the second turn's ``_maybe_microcompact`` re-evaluates and fires
    # again.
    assert microcompactor.microcompact_calls == 2


# ---------------------------------------------------------------------------
# 8c. Snip redundant tool results after microcompact and before compaction
# ---------------------------------------------------------------------------

def test_agent_loop_snips_before_context_building() -> None:
    recent_timestamp = datetime.now(UTC).isoformat()
    transcript = Transcript()
    for i in range(3):
        for msg in _tool_exchange_messages(
            tool_use_id=f"read-{i}",
            result_content=f"read result {i}",
            timestamp=recent_timestamp,
        ):
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
    assert SNIPPED_CONTENT in sent_context
    assert "read result 0" not in sent_context
    assert "read result 2" in sent_context


def test_agent_loop_run_snip_order_is_after_microcompact_before_compaction() -> None:
    events: list[str] = []
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(
        p,
        microcompactor=_OrderingMicroCompactor(events),
        snip_tool=_OrderingSnipTool(events),
        compactor=_OrderingCompactor(events),
    )

    result = loop.run("hello")

    assert result.status == LoopStatus.COMPLETED
    assert events[:5] == [
        "micro_should",
        "micro_apply",
        "snip_should",
        "snip_apply",
        "compact_should",
    ]


def test_agent_loop_run_stream_snip_order_is_after_microcompact_before_compaction() -> None:
    events: list[str] = []
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(
        p,
        microcompactor=_OrderingMicroCompactor(events),
        snip_tool=_OrderingSnipTool(events),
        compactor=_OrderingCompactor(events),
    )

    stream_events = list(loop.run_stream("hello"))

    assert stream_events[-1].result is not None
    assert stream_events[-1].result.status == LoopStatus.COMPLETED
    assert events[:5] == [
        "micro_should",
        "micro_apply",
        "snip_should",
        "snip_apply",
        "compact_should",
    ]


def test_agent_loop_snip_attempted_only_once_within_same_user_turn() -> None:
    events: list[str] = []
    snip_tool = _OrderingSnipTool(events)
    echo = Tool(name="echo", description="", input_schema={}, fn=lambda text: text)
    p = MockProvider([
        MockProvider.tool_call("echo", {"text": "first"}, id="tu_echo"),
        MockProvider.direct_answer("done"),
    ])
    loop, _, _ = _make_loop(p, tools=[echo], snip_tool=snip_tool)

    result = loop.run("call echo")

    assert result.status == LoopStatus.COMPLETED
    assert snip_tool.should_calls == 1
    assert snip_tool.snip_calls == 1


def test_agent_loop_snip_attempt_flag_resets_next_user_turn() -> None:
    events: list[str] = []
    snip_tool = _OrderingSnipTool(events)
    p = MockProvider([
        MockProvider.direct_answer("first"),
        MockProvider.direct_answer("second"),
    ])
    loop, _, _ = _make_loop(p, snip_tool=snip_tool)

    first = loop.run("first request")
    second = loop.run("second request")

    assert first.status == LoopStatus.COMPLETED
    assert second.status == LoopStatus.COMPLETED
    assert snip_tool.should_calls == 2
    assert snip_tool.snip_calls == 2


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


# ---------------------------------------------------------------------------
# M3: recent-file snapshot capture in _execute_one
# ---------------------------------------------------------------------------

def test_execute_one_captures_read_file_snapshot() -> None:
    loop, _, _ = _make_loop(MockProvider([]), tools=[_read_file_tool("HELLO BODY")])
    loop._execute_one(ToolCall(id="t1", name="read_file", input={"path": "a.py"}))
    snaps = list(loop._recent_file_snapshots)
    assert len(snaps) == 1
    assert snaps[0].path == "a.py"
    assert snaps[0].content == "HELLO BODY"
    assert snaps[0].captured_at != ""


def test_execute_one_skips_non_read_file_tool() -> None:
    write_tool = Tool(
        name="write_file",
        description="write",
        input_schema={"type": "object"},
        fn=lambda path, content: "ok",
    )
    loop, _, _ = _make_loop(MockProvider([]), tools=[write_tool])
    loop._execute_one(
        ToolCall(id="t1", name="write_file", input={"path": "a.py", "content": "x"})
    )
    assert len(loop._recent_file_snapshots) == 0


def test_execute_one_skips_failed_read_file() -> None:
    def boom(path: str) -> str:
        raise RuntimeError("cannot read")

    failing = Tool(
        name="read_file",
        description="read",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        fn=boom,
    )
    loop, _, _ = _make_loop(MockProvider([]), tools=[failing])
    result = loop._execute_one(ToolCall(id="t1", name="read_file", input={"path": "a.py"}))
    assert result.is_error is True
    assert len(loop._recent_file_snapshots) == 0


def test_recent_file_snapshots_capped_at_five() -> None:
    loop, _, _ = _make_loop(MockProvider([]), tools=[_read_file_tool("BODY")])
    for i in range(6):
        loop._execute_one(
            ToolCall(id=f"t{i}", name="read_file", input={"path": f"f{i}.py"})
        )
    snaps = list(loop._recent_file_snapshots)
    assert len(snaps) == 5
    # Oldest (f0.py) evicted; newest five retained.
    assert [s.path for s in snaps] == ["f1.py", "f2.py", "f3.py", "f4.py", "f5.py"]


def test_recent_file_snapshots_newest_wins_per_path() -> None:
    loop, _, _ = _make_loop(MockProvider([]), tools=[_read_file_tool("OLD")])
    loop._execute_one(ToolCall(id="t1", name="read_file", input={"path": "a.py"}))
    # Swap the tool to return new content for the same path.
    loop._tool_executor = ToolExecutor(_registry_with(_read_file_tool("NEW")))
    loop._execute_one(ToolCall(id="t2", name="read_file", input={"path": "a.py"}))
    snaps = list(loop._recent_file_snapshots)
    assert len(snaps) == 1
    assert snaps[0].content == "NEW"


def test_force_compact_passes_snapshots_into_summary() -> None:
    compactor = ContextCompactor(keep_recent=1, compact_threshold=1.0)
    loop, t, _ = _make_loop(
        MockProvider([]), tools=[_read_file_tool("BODY")], compactor=compactor
    )
    t.append(Message.user("hello there"))
    loop._execute_one(ToolCall(id="t1", name="read_file", input={"path": "a.py"}))
    loop._force_compact()
    assert loop._last_summary is not None
    assert [s.path for s in loop._last_summary.recent_file_snapshots] == ["a.py"]


def test_force_compact_snapshot_is_point_in_time() -> None:
    compactor = ContextCompactor(keep_recent=1, compact_threshold=1.0)
    loop, t, _ = _make_loop(
        MockProvider([]), tools=[_read_file_tool("BODY")], compactor=compactor
    )
    t.append(Message.user("hello there"))
    loop._execute_one(ToolCall(id="t1", name="read_file", input={"path": "a.py"}))
    loop._force_compact()
    # A read AFTER compaction must not retroactively mutate the prior summary.
    loop._execute_one(ToolCall(id="t2", name="read_file", input={"path": "b.py"}))
    assert loop._last_summary is not None
    assert [s.path for s in loop._last_summary.recent_file_snapshots] == ["a.py"]
    # ...but the live deque now carries both.
    assert {s.path for s in loop._recent_file_snapshots} == {"a.py", "b.py"}


def _registry_with(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for t in tools:
        registry.register(t)
    return registry


# ---------------------------------------------------------------------------
# M4: model-driven snip nudge — token growth, arming, suppression, resets
# ---------------------------------------------------------------------------


class _NeverSnip(SnipTool):
    def should_snip(self, messages: list[Message]) -> bool:
        return False


class _AlwaysSnip(SnipTool):
    def should_snip(self, messages: list[Message]) -> bool:
        return True

    def snip(self, messages: list[Message]) -> list[Message]:
        return list(messages)


def _snippable_pairs(n: int, *, trailing_user_text: bool = True) -> list[Message]:
    ts = datetime.now(UTC).isoformat()
    msgs: list[Message] = [Message.user("start")]
    for i in range(n):
        msgs.append(Message(
            uuid=f"a-{i}", role=Role.ASSISTANT,
            content=[ToolCall(id=f"tc-{i}", name="read_file", input={"path": "f.py"})],
            timestamp=ts, type=MessageType.TOOL_USE,
        ))
        msgs.append(Message(
            uuid=f"r-{i}", role=Role.USER,
            content=[ToolResult(tool_use_id=f"tc-{i}", content=f"data-{i}")],
            timestamp=ts, type=MessageType.TOOL_RESULT, is_meta=True,
        ))
    if trailing_user_text:
        msgs.append(Message.user("current turn"))
    return msgs


def test_track_growth_accumulates_on_tool_turn() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p)
    asst = Message(
        uuid="a", role=Role.ASSISTANT,
        content=[ToolCall(id="t1", name="read_file", input={"path": "f.py"})],
        timestamp="t", type=MessageType.TOOL_USE,
    )
    results = [ToolResult(tool_use_id="t1", content="x" * 400)]
    loop._track_snip_nudge_growth(asst, results)
    assert loop._tokens_since_last_snip > 0


def test_track_growth_resets_on_model_snip_call() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p)
    loop._tokens_since_last_snip = 5_000
    asst = Message(
        uuid="a", role=Role.ASSISTANT,
        content=[ToolCall(id="t1", name="snip_history", input={"message_uuids": ["r-0"]})],
        timestamp="t", type=MessageType.TOOL_USE,
    )
    results = [ToolResult(tool_use_id="t1", content="Snipped 1 messages", is_error=False)]
    loop._track_snip_nudge_growth(asst, results)
    assert loop._tokens_since_last_snip == 0


def test_track_growth_not_reset_on_failed_model_snip() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p)
    loop._tokens_since_last_snip = 100
    asst = Message(
        uuid="a", role=Role.ASSISTANT,
        content=[ToolCall(id="t1", name="snip_history", input={"message_uuids": ["x"]})],
        timestamp="t", type=MessageType.TOOL_USE,
    )
    results = [ToolResult(tool_use_id="t1", content="snip refused: x", is_error=True)]
    loop._track_snip_nudge_growth(asst, results)
    assert loop._tokens_since_last_snip > 100


def test_force_compact_resets_tokens_since_last_snip() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, compactor=_CountingCompactor())
    loop._tokens_since_last_snip = 9_999
    loop._force_compact()
    assert loop._tokens_since_last_snip == 0


def test_engine_snip_resets_tokens_since_last_snip() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, snip_tool=_AlwaysSnip())
    loop._tokens_since_last_snip = 8_000
    loop._snip_attempted_this_turn = False
    assert loop._maybe_snip() is True
    assert loop._tokens_since_last_snip == 0


def test_compute_nudge_arms_when_growth_exceeds_threshold() -> None:
    t = Transcript()
    t.replace_all(_snippable_pairs(8))
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, transcript=t)
    loop._tokens_since_last_snip = loop._snip_nudge_growth_tokens
    nudge = loop._compute_snip_nudge()
    assert nudge is not None
    assert nudge.candidate_uuids == tuple(snippable_candidate_uuids(t.all_messages()))
    assert nudge.candidate_uuids == ("r-0", "r-1", "r-2")


def test_compute_nudge_none_below_threshold() -> None:
    t = Transcript()
    t.replace_all(_snippable_pairs(8))
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, transcript=t)
    loop._tokens_since_last_snip = loop._snip_nudge_growth_tokens - 1
    assert loop._compute_snip_nudge() is None


def test_compute_nudge_none_when_no_candidates() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p)  # empty transcript
    loop._tokens_since_last_snip = loop._snip_nudge_growth_tokens * 2
    assert loop._compute_snip_nudge() is None


def test_compute_nudge_suppressed_when_flag_set() -> None:
    t = Transcript()
    t.replace_all(_snippable_pairs(8))
    p = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, _ = _make_loop(p, transcript=t)
    loop._tokens_since_last_snip = loop._snip_nudge_growth_tokens * 2
    loop._snip_nudge_suppressed = True
    assert loop._compute_snip_nudge() is None


def test_reactive_compact_suppresses_subsequent_nudge() -> None:
    # Reactive compact fires once; afterwards even high growth + candidates
    # must not arm a nudge for the rest of the loop's life.
    provider = _PromptTooLongThenProvider([
        PromptTooLongError("prompt too long"),
        MockProvider.direct_answer("recovered"),
    ])
    loop, _, _ = _make_loop(provider, compactor=_CountingCompactor())
    result = loop.run("large request")
    assert result.status == LoopStatus.COMPLETED
    assert loop._snip_nudge_suppressed is True

    # Re-seed candidates + growth and confirm the nudge stays suppressed.
    loop._transcript.replace_all(_snippable_pairs(8))
    loop._tokens_since_last_snip = loop._snip_nudge_growth_tokens * 2
    assert loop._compute_snip_nudge() is None


def test_model_snip_via_tool_mutates_live_transcript() -> None:
    # §4 integration: the snip_history tool registered against the loop's
    # transcript removes a targeted uuid during a real run().
    t = Transcript()
    t.replace_all(_snippable_pairs(6, trailing_user_text=False))
    provider = MockProvider([
        MockProvider.tool_call("snip_history", {"message_uuids": ["r-0"]}, id="tu_snip"),
        MockProvider.direct_answer("cleaned"),
    ])
    loop, transcript, registry = _make_loop(provider, transcript=t, snip_tool=_NeverSnip())
    register_snip_history_tool(registry, transcript)

    result = loop.run("please clean up old reads")

    assert result.status == LoopStatus.COMPLETED
    uuids = {m.uuid for m in transcript.all_messages()}
    assert "r-0" not in uuids
    assert {"r-1", "r-2", "r-3", "r-4", "r-5"} <= uuids
    # A successful model snip resets the growth window.
    assert loop._tokens_since_last_snip == 0


def test_snip_nudge_growth_tokens_must_be_positive() -> None:
    import pytest

    budget = ContextBudget(max_tokens=1000, reserved_output_tokens=100)
    with pytest.raises(ValueError, match="snip_nudge_growth_tokens"):
        AgentLoop(
            provider=MockProvider([MockProvider.direct_answer("x")]),
            tool_executor=ToolExecutor(ToolRegistry()),
            transcript=Transcript(),
            context_builder=ContextBuilder(budget=budget),
            budget=budget,
            snip_nudge_growth_tokens=0,
        )
