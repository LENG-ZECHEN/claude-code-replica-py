"""Phase 7 / Step 1: Provider tests — written before implementation (TDD).

Covers:
  TokenUsage         — token accounting dataclass
  ProviderResponse   — final-text vs tool-call vs malformed shape
  Provider Protocol  — duck-typed interface
  MockProvider       — scripted responses, exhaustion, call history, convenience builders
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from simple_coding_agent.models import ToolCall
from simple_coding_agent.provider import (
    STOP_MAX_TOKENS,
    STOP_TOOL_USE,
    MockProvider,
    OpenAIProvider,
    PromptTooLongError,
    Provider,
    ProviderCall,
    ProviderResponse,
    TokenUsage,
)


class _FakeChatCompletions:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class _FakeChat:
    def __init__(self, response: object) -> None:
        self.completions = _FakeChatCompletions(response)


class _FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.chat = _FakeChat(response)


class _RaisingChatCompletions:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        raise self.exc


class _RaisingChat:
    def __init__(self, exc: Exception) -> None:
        self.completions = _RaisingChatCompletions(exc)


class _RaisingOpenAIClient:
    def __init__(self, exc: Exception) -> None:
        self.chat = _RaisingChat(exc)

# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------

def test_token_usage_defaults_are_zero() -> None:
    u = TokenUsage()
    assert u.input_tokens == 0
    assert u.output_tokens == 0
    assert u.cache_read_input_tokens == 0
    assert u.cache_creation_input_tokens == 0


def test_token_usage_total_sums_all_fields() -> None:
    u = TokenUsage(
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=5,
        cache_creation_input_tokens=3,
    )
    assert u.total == 38


def test_token_usage_total_with_only_input_output() -> None:
    u = TokenUsage(input_tokens=100, output_tokens=50)
    assert u.total == 150


# ---------------------------------------------------------------------------
# ProviderResponse
# ---------------------------------------------------------------------------

def test_provider_response_direct_text_answer() -> None:
    r = ProviderResponse(
        text="hello",
        tool_calls=[],
        usage=TokenUsage(),
        stop_reason="end_turn",
    )
    assert r.text == "hello"
    assert r.tool_calls == []
    assert r.stop_reason == "end_turn"


def test_provider_response_tool_call_response() -> None:
    tc = ToolCall(id="tu_1", name="read_file", input={"path": "x.py"})
    r = ProviderResponse(
        text=None,
        tool_calls=[tc],
        usage=TokenUsage(),
        stop_reason="tool_use",
    )
    assert r.text is None
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0].name == "read_file"
    assert r.stop_reason == "tool_use"


def test_provider_response_malformed_has_no_text_and_no_tools() -> None:
    """A response with neither text nor tool calls is malformed."""
    r = ProviderResponse(
        text=None,
        tool_calls=[],
        usage=TokenUsage(),
        stop_reason="end_turn",
    )
    assert r.text is None
    assert r.tool_calls == []


# ---------------------------------------------------------------------------
# Provider Protocol (duck typing)
# ---------------------------------------------------------------------------

def test_mock_provider_satisfies_provider_protocol() -> None:
    p: Provider = MockProvider([MockProvider.direct_answer("ok")])
    r = p.call(system="", messages=[], tools=[])
    assert isinstance(r, ProviderResponse)


# ---------------------------------------------------------------------------
# MockProvider — basic behavior
# ---------------------------------------------------------------------------

def test_mock_provider_returns_first_scripted_response() -> None:
    expected = ProviderResponse(
        text="hi",
        tool_calls=[],
        usage=TokenUsage(input_tokens=1, output_tokens=1),
        stop_reason="end_turn",
    )
    p = MockProvider([expected])
    result = p.call(system="", messages=[], tools=[])
    assert result is expected


def test_mock_provider_returns_responses_in_order() -> None:
    r1 = MockProvider.direct_answer("a")
    r2 = MockProvider.direct_answer("b")
    r3 = MockProvider.direct_answer("c")
    p = MockProvider([r1, r2, r3])
    assert p.call(system="", messages=[], tools=[]).text == "a"
    assert p.call(system="", messages=[], tools=[]).text == "b"
    assert p.call(system="", messages=[], tools=[]).text == "c"


def test_mock_provider_raises_when_script_exhausted() -> None:
    p = MockProvider([MockProvider.direct_answer("only")])
    p.call(system="", messages=[], tools=[])
    with pytest.raises(IndexError):
        p.call(system="", messages=[], tools=[])


def test_mock_provider_empty_script_raises_on_first_call() -> None:
    p = MockProvider([])
    with pytest.raises(IndexError):
        p.call(system="", messages=[], tools=[])


# ---------------------------------------------------------------------------
# MockProvider — call history
# ---------------------------------------------------------------------------

def test_mock_provider_records_call_history() -> None:
    p = MockProvider([MockProvider.direct_answer("ok")])
    p.call(
        system="you are helpful",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    assert len(p.history) == 1
    entry = p.history[0]
    assert isinstance(entry, ProviderCall)
    assert entry.system == "you are helpful"
    assert entry.messages == [{"role": "user", "content": "hi"}]


def test_mock_provider_history_records_each_call() -> None:
    p = MockProvider([
        MockProvider.direct_answer("a"),
        MockProvider.direct_answer("b"),
    ])
    p.call(system="s1", messages=[{"role": "user", "content": "1"}], tools=[])
    p.call(system="s2", messages=[{"role": "user", "content": "2"}], tools=[])
    assert len(p.history) == 2
    assert p.history[0].system == "s1"
    assert p.history[1].system == "s2"


def test_mock_provider_history_is_a_copy() -> None:
    """Mutating the returned history list must not affect internal state."""
    p = MockProvider([MockProvider.direct_answer("ok")])
    p.call(system="", messages=[], tools=[])
    h = p.history
    h.clear()
    assert len(p.history) == 1


# ---------------------------------------------------------------------------
# MockProvider — convenience builders
# ---------------------------------------------------------------------------

def test_direct_answer_builder() -> None:
    r = MockProvider.direct_answer("done")
    assert r.text == "done"
    assert r.tool_calls == []
    assert r.stop_reason == "end_turn"


def test_tool_call_builder() -> None:
    r = MockProvider.tool_call(name="read_file", input={"path": "x"}, id="tu_1")
    assert r.text is None
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0].name == "read_file"
    assert r.tool_calls[0].input == {"path": "x"}
    assert r.tool_calls[0].id == "tu_1"
    assert r.stop_reason == "tool_use"


def test_tool_call_builder_generates_id_when_omitted() -> None:
    r = MockProvider.tool_call(name="echo", input={"text": "hi"})
    assert r.tool_calls[0].id != ""


def test_malformed_builder() -> None:
    r = MockProvider.malformed()
    assert r.text is None
    assert r.tool_calls == []


# ---------------------------------------------------------------------------
# MockProvider — scripted scenarios called out in the Phase 7 instructions
# ---------------------------------------------------------------------------

def test_scenario_direct_final_answer() -> None:
    p = MockProvider([MockProvider.direct_answer("the answer")])
    result = p.call(system="", messages=[], tools=[])
    assert result.text == "the answer"
    assert result.stop_reason == "end_turn"


def test_scenario_single_tool_then_final_answer() -> None:
    p = MockProvider([
        MockProvider.tool_call("read_file", {"path": "x"}, id="tu_1"),
        MockProvider.direct_answer("file is empty"),
    ])
    assert p.call(system="", messages=[], tools=[]).stop_reason == "tool_use"
    assert p.call(system="", messages=[], tools=[]).text == "file is empty"


def test_scenario_multiple_tool_calls_then_final_answer() -> None:
    p = MockProvider([
        MockProvider.tool_call("list_files", {"path": "."}, id="tu_1"),
        MockProvider.tool_call("read_file", {"path": "main.py"}, id="tu_2"),
        MockProvider.direct_answer("done"),
    ])
    r1 = p.call(system="", messages=[], tools=[])
    r2 = p.call(system="", messages=[], tools=[])
    r3 = p.call(system="", messages=[], tools=[])
    assert r1.tool_calls[0].name == "list_files"
    assert r2.tool_calls[0].name == "read_file"
    assert r3.text == "done"


def test_scenario_repeated_tool_call() -> None:
    """Two identical tool names with different IDs."""
    p = MockProvider([
        MockProvider.tool_call("read_file", {"path": "x"}, id="tu_1"),
        MockProvider.tool_call("read_file", {"path": "x"}, id="tu_2"),
        MockProvider.direct_answer("done"),
    ])
    assert p.call(system="", messages=[], tools=[]).tool_calls[0].id == "tu_1"
    assert p.call(system="", messages=[], tools=[]).tool_calls[0].id == "tu_2"
    assert p.call(system="", messages=[], tools=[]).text == "done"


def test_scenario_malformed_response() -> None:
    p = MockProvider([MockProvider.malformed()])
    r = p.call(system="", messages=[], tools=[])
    assert r.text is None
    assert r.tool_calls == []


def test_scenario_max_steps_endless_tool_calls() -> None:
    """A script with more tool calls than any reasonable max_steps."""
    script = [MockProvider.tool_call("loop_tool", {}, id=f"tu_{i}") for i in range(20)]
    p = MockProvider(script)
    for i in range(20):
        r = p.call(system="", messages=[], tools=[])
        assert r.stop_reason == "tool_use"
        assert r.tool_calls[0].id == f"tu_{i}"


# ---------------------------------------------------------------------------
# OpenAIProvider — Chat Completions adapter
# ---------------------------------------------------------------------------

def _completion(
    *,
    content: str | None = "done",
    tool_calls: list[object] | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 3,
) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=tool_calls),
                finish_reason=finish_reason,
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )


def _stream_chunk(
    *,
    content: str | None = None,
    tool_calls: list[object] | None = None,
    finish_reason: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> object:
    usage = None
    if prompt_tokens is not None or completion_tokens is not None:
        usage = SimpleNamespace(
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
        )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content, tool_calls=tool_calls),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def test_openai_provider_translates_request_shapes() -> None:
    client = _FakeOpenAIClient(_completion(content="ok"))
    provider = OpenAIProvider(model="test-model", max_tokens=123, client=client)

    result = provider.call(
        system="system prompt",
        messages=[
            {"role": "user", "content": "read the file"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "read_file",
                        "input": {"path": "x.py"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "file contents"}
                ],
            },
        ],
        tools=[
            {
                "name": "read_file",
                "description": "Read a file.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
    )

    call = client.chat.completions.calls[0]
    assert call["model"] == "test-model"
    assert call["max_tokens"] == 123
    assert call["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "read the file"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tu_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"x.py"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tu_1", "content": "file contents"},
    ]
    assert call["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]
    assert call["tool_choice"] == "auto"
    assert result.text == "ok"


def test_openai_provider_parses_tool_calls() -> None:
    raw_tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="read_file", arguments='{"path":"README.md"}'),
    )
    client = _FakeOpenAIClient(_completion(
        content="I will read it.",
        tool_calls=[raw_tool_call],
        finish_reason="tool_calls",
    ))
    provider = OpenAIProvider(model="test-model", client=client)

    result = provider.call(system="", messages=[], tools=[])

    assert result.stop_reason == STOP_TOOL_USE
    assert result.text == "I will read it."
    assert result.tool_calls == [
        ToolCall(id="call_1", name="read_file", input={"path": "README.md"})
    ]
    assert result.usage == TokenUsage(input_tokens=10, output_tokens=3)


def test_openai_provider_maps_length_to_max_tokens() -> None:
    client = _FakeOpenAIClient(_completion(
        content="partial",
        finish_reason="length",
        prompt_tokens=5,
        completion_tokens=7,
    ))
    provider = OpenAIProvider(model="test-model", client=client)

    result = provider.call(system="", messages=[], tools=[])

    assert result.stop_reason == STOP_MAX_TOKENS
    assert result.text == "partial"
    assert result.usage.total == 12


def test_openai_provider_maps_context_errors_to_prompt_too_long() -> None:
    original = RuntimeError("maximum context length exceeded")
    provider = OpenAIProvider(model="test-model", client=_RaisingOpenAIClient(original))

    with pytest.raises(PromptTooLongError) as exc_info:
        provider.call(system="", messages=[], tools=[])

    assert exc_info.value.__cause__ is original


def test_openai_provider_does_not_map_non_context_errors() -> None:
    original = RuntimeError("temporary upstream outage")
    provider = OpenAIProvider(model="test-model", client=_RaisingOpenAIClient(original))

    with pytest.raises(RuntimeError, match="temporary upstream outage") as exc_info:
        provider.call(system="", messages=[], tools=[])

    assert exc_info.value is original


def test_openai_provider_rejects_non_object_tool_arguments() -> None:
    raw_tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="read_file", arguments='["not", "object"]'),
    )
    client = _FakeOpenAIClient(_completion(
        content=None,
        tool_calls=[raw_tool_call],
        finish_reason="tool_calls",
    ))
    provider = OpenAIProvider(model="test-model", client=client)

    with pytest.raises(ValueError, match="arguments"):
        provider.call(system="", messages=[], tools=[])


def test_openai_provider_rejects_invalid_json_tool_arguments() -> None:
    raw_tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="read_file", arguments="{bad json"),
    )
    client = _FakeOpenAIClient(_completion(
        content=None,
        tool_calls=[raw_tool_call],
        finish_reason="tool_calls",
    ))
    provider = OpenAIProvider(model="test-model", client=client)

    with pytest.raises(ValueError, match="valid JSON"):
        provider.call(system="", messages=[], tools=[])


def test_openai_provider_streams_text_deltas() -> None:
    client = _FakeOpenAIClient([
        _stream_chunk(content="Hel"),
        _stream_chunk(content="lo", finish_reason="stop", prompt_tokens=4, completion_tokens=2),
    ])
    provider = OpenAIProvider(model="test-model", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    assert client.chat.completions.calls[0]["stream"] is True
    assert [event.text for event in events if event.type == "text_delta"] == ["Hel", "lo"]
    done = events[-1].response
    assert done is not None
    assert done.text == "Hello"
    assert done.stop_reason == "end_turn"
    assert done.usage == TokenUsage(input_tokens=4, output_tokens=2)


def test_openai_provider_streams_tool_call_argument_fragments() -> None:
    first_tool_delta = SimpleNamespace(
        index=0,
        id="call_1",
        function=SimpleNamespace(name="read_file", arguments='{"path"'),
    )
    second_tool_delta = SimpleNamespace(
        index=0,
        function=SimpleNamespace(arguments=':"README.md"}'),
    )
    client = _FakeOpenAIClient([
        _stream_chunk(content="I will read it."),
        _stream_chunk(tool_calls=[first_tool_delta]),
        _stream_chunk(tool_calls=[second_tool_delta], finish_reason="tool_calls"),
    ])
    provider = OpenAIProvider(model="test-model", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    assert [event.text for event in events if event.type == "text_delta"] == ["I will read it."]
    done = events[-1].response
    assert done is not None
    assert done.stop_reason == STOP_TOOL_USE
    assert done.text == "I will read it."
    assert done.tool_calls == [
        ToolCall(id="call_1", name="read_file", input={"path": "README.md"})
    ]


def test_openai_provider_stream_repairs_flat_tool_arguments_with_unescaped_quotes() -> None:
    """Some OpenAI-compatible streams emit nearly-JSON tool args for long writes."""
    tool_delta = SimpleNamespace(
        index=0,
        id="call_1",
        function=SimpleNamespace(
            name="write_file",
            arguments=(
                '{"path":"REPORT.md","content":"Summary mentions "AgentLoop" '
                'and keeps going"}'
            ),
        ),
    )
    client = _FakeOpenAIClient([
        _stream_chunk(tool_calls=[tool_delta], finish_reason="tool_calls"),
    ])
    provider = OpenAIProvider(model="test-model", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    assert done.stop_reason == STOP_TOOL_USE
    assert done.tool_calls == [
        ToolCall(
            id="call_1",
            name="write_file",
            input={
                "path": "REPORT.md",
                "content": 'Summary mentions "AgentLoop" and keeps going',
            },
        )
    ]


def test_openai_provider_stream_maps_length_to_max_tokens() -> None:
    client = _FakeOpenAIClient([
        _stream_chunk(content="partial", finish_reason="length"),
    ])
    provider = OpenAIProvider(model="test-model", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    assert done.text == "partial"
    assert done.stop_reason == STOP_MAX_TOKENS


def test_openai_provider_stream_maps_context_errors_to_prompt_too_long() -> None:
    original = RuntimeError("input is too large for the token limit")
    provider = OpenAIProvider(model="test-model", client=_RaisingOpenAIClient(original))

    with pytest.raises(PromptTooLongError) as exc_info:
        list(provider.stream_call(system="", messages=[], tools=[]))

    assert exc_info.value.__cause__ is original
