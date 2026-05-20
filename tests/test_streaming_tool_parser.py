"""Targeted tests for OpenAI streaming tool-call parsing.

Covers the contract documented in the takeover request:
  - normal one-piece JSON arguments
  - arguments split across many chunks (merged by tool_call index)
  - arguments containing Chinese text, newlines, quotes, escapes
  - multiple tool calls in the same assistant message
  - empty deltas before valid argument chunks
  - malformed final JSON does NOT crash; surfaces as a controlled
    `ProviderResponse` text payload with `stop_reason="end_turn"`

The OpenAI client is faked; no network call is made.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from simple_coding_agent.models import ToolCall
from simple_coding_agent.provider import (
    STOP_END_TURN,
    STOP_TOOL_USE,
    OpenAIProvider,
    StreamToolParseError,
    _parse_openai_stream_tool_calls,
)

# ---------------------------------------------------------------------------
# Direct unit tests of _parse_openai_stream_tool_calls
# ---------------------------------------------------------------------------

def test_parse_one_piece_arguments() -> None:
    parts = {0: {"id": "call_1", "name": "read_file", "arguments": '{"path":"README.md"}'}}
    result = _parse_openai_stream_tool_calls(parts)
    assert result == [ToolCall(id="call_1", name="read_file", input={"path": "README.md"})]


def test_parse_accumulated_fragments_form_valid_json() -> None:
    """Simulate `arguments` already accumulated from many chunks."""
    accumulated = '{"pa' + 'th": ' + '"README' + '.md"}'
    parts = {0: {"id": "call_1", "name": "read_file", "arguments": accumulated}}
    result = _parse_openai_stream_tool_calls(parts)
    assert result[0].input == {"path": "README.md"}


def test_parse_arguments_with_chinese_and_newlines() -> None:
    accumulated = '{"path": "src/中文/说明.md", "content": "第一行\\n第二行"}'
    parts = {0: {"id": "call_1", "name": "write_file", "arguments": accumulated}}
    result = _parse_openai_stream_tool_calls(parts)
    assert result[0].input == {
        "path": "src/中文/说明.md",
        "content": "第一行\n第二行",
    }


def test_parse_arguments_with_escaped_quotes_and_backslashes() -> None:
    accumulated = r'{"text": "say \"hi\" and a path C:\\\\tmp"}'
    parts = {0: {"id": "call_1", "name": "write_file", "arguments": accumulated}}
    result = _parse_openai_stream_tool_calls(parts)
    assert result[0].input == {"text": 'say "hi" and a path C:\\\\tmp'}


def test_parse_multiple_tool_calls_merged_by_index() -> None:
    parts = {
        0: {"id": "call_1", "name": "list_files", "arguments": "{}"},
        1: {"id": "call_2", "name": "read_file", "arguments": '{"path":"a.py"}'},
    }
    result = _parse_openai_stream_tool_calls(parts)
    assert [tc.name for tc in result] == ["list_files", "read_file"]
    assert result[0].input == {}
    assert result[1].input == {"path": "a.py"}


def test_parse_malformed_arguments_raises_controlled_error() -> None:
    parts = {0: {"id": "call_1", "name": "write_file", "arguments": "{ not valid"}}
    with pytest.raises(StreamToolParseError) as excinfo:
        _parse_openai_stream_tool_calls(parts)
    error = excinfo.value
    assert error.partial_tool_calls == []
    assert len(error.failures) == 1
    failure = error.failures[0]
    assert failure.index == 0
    assert failure.id == "call_1"
    assert failure.name == "write_file"
    assert failure.raw_arguments == "{ not valid"


def test_parse_partial_failure_retains_successful_calls() -> None:
    parts = {
        0: {"id": "call_1", "name": "list_files", "arguments": "{}"},
        1: {"id": "call_2", "name": "write_file", "arguments": "{broken"},
    }
    with pytest.raises(StreamToolParseError) as excinfo:
        _parse_openai_stream_tool_calls(parts)
    error = excinfo.value
    assert len(error.partial_tool_calls) == 1
    assert error.partial_tool_calls[0].name == "list_files"
    assert error.failures[0].name == "write_file"


def test_stream_tool_parse_error_subclasses_value_error() -> None:
    """Existing tests that catch ValueError must continue to match."""
    parts = {0: {"id": "call_1", "name": "x", "arguments": "{bad"}}
    with pytest.raises(ValueError):
        _parse_openai_stream_tool_calls(parts)


# ---------------------------------------------------------------------------
# OpenAIProvider.stream_call end-to-end (fake client)
# ---------------------------------------------------------------------------

class _FakeChatCompletions:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class _FakeChat:
    def __init__(self, response: object) -> None:
        self.completions = _FakeChatCompletions(response)


class _FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.chat = _FakeChat(response)


def _chunk(
    *,
    content: str | None = None,
    tool_calls: list[object] | None = None,
    finish_reason: str | None = None,
) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content, tool_calls=tool_calls),
                finish_reason=finish_reason,
            )
        ],
        usage=None,
    )


def _tool_delta(
    *,
    index: int,
    id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> object:
    return SimpleNamespace(
        index=index,
        id=id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_stream_call_accumulates_arguments_across_many_chunks() -> None:
    client = _FakeOpenAIClient([
        _chunk(tool_calls=[
            _tool_delta(index=0, id="call_1", name="read_file", arguments='{"pa'),
        ]),
        _chunk(tool_calls=[_tool_delta(index=0, arguments='th":')]),
        _chunk(tool_calls=[_tool_delta(index=0, arguments=' "RE')]),
        _chunk(
            tool_calls=[_tool_delta(index=0, arguments='ADME.md"}')],
            finish_reason="tool_calls",
        ),
    ])
    provider = OpenAIProvider(model="m", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    assert done.stop_reason == STOP_TOOL_USE
    assert done.tool_calls == [
        ToolCall(id="call_1", name="read_file", input={"path": "README.md"})
    ]


def test_stream_call_supports_chinese_and_newlines_in_arguments() -> None:
    client = _FakeOpenAIClient([
        _chunk(tool_calls=[
            _tool_delta(index=0, id="call_1", name="write_file",
                        arguments='{"path":"中文/说明.md","content":"第一行\\n第二行"}'),
        ], finish_reason="tool_calls"),
    ])
    provider = OpenAIProvider(model="m", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    assert done.tool_calls[0].input == {
        "path": "中文/说明.md",
        "content": "第一行\n第二行",
    }


def test_stream_call_handles_multiple_tool_calls_in_same_response() -> None:
    client = _FakeOpenAIClient([
        _chunk(tool_calls=[_tool_delta(index=0, id="call_1", name="list_files", arguments="{}")]),
        _chunk(tool_calls=[
            _tool_delta(index=1, id="call_2", name="read_file", arguments='{"path":"a.py"}'),
        ], finish_reason="tool_calls"),
    ])
    provider = OpenAIProvider(model="m", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    assert [tc.name for tc in done.tool_calls] == ["list_files", "read_file"]
    assert done.tool_calls[1].input == {"path": "a.py"}


def test_stream_call_tolerates_empty_deltas_before_real_arguments() -> None:
    client = _FakeOpenAIClient([
        _chunk(),                # no delta content
        _chunk(content=""),      # empty text delta
        _chunk(tool_calls=[]),   # empty tool_calls list
        _chunk(tool_calls=[
            _tool_delta(index=0, id="call_1", name="list_files", arguments=""),
        ]),
        _chunk(
            tool_calls=[_tool_delta(index=0, arguments="{}")],
            finish_reason="tool_calls",
        ),
    ])
    provider = OpenAIProvider(model="m", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    assert done.tool_calls == [
        ToolCall(id="call_1", name="list_files", input={})
    ]


def test_stream_call_does_not_crash_on_malformed_final_arguments() -> None:
    """The whole point of the controlled-error path."""
    client = _FakeOpenAIClient([
        _chunk(content="I will try."),
        _chunk(tool_calls=[
            _tool_delta(index=0, id="call_1", name="write_file",
                        arguments='{not even close to JSON'),
        ], finish_reason="tool_calls"),
    ])
    provider = OpenAIProvider(model="m", client=client)

    # Must not raise; must yield a done event we can read.
    events = list(provider.stream_call(system="", messages=[], tools=[]))

    text_deltas = [e.text for e in events if e.type == "text_delta"]
    assert text_deltas == ["I will try."]

    done_events = [e for e in events if e.type == "done"]
    assert len(done_events) == 1
    response = done_events[0].response
    assert response is not None
    assert response.tool_calls == []
    assert response.stop_reason == STOP_END_TURN
    assert response.text is not None
    assert "I will try." in response.text
    assert "could not be parsed" in response.text
    assert "write_file" in response.text


def test_stream_call_malformed_partial_drops_all_tool_calls() -> None:
    """One valid + one malformed → all tool calls dropped (all-or-nothing)."""
    client = _FakeOpenAIClient([
        _chunk(tool_calls=[
            _tool_delta(index=0, id="call_1", name="list_files", arguments="{}"),
        ]),
        _chunk(tool_calls=[
            _tool_delta(index=1, id="call_2", name="write_file",
                        arguments="{broken"),
        ], finish_reason="tool_calls"),
    ])
    provider = OpenAIProvider(model="m", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    assert done.tool_calls == []
    assert "write_file" in (done.text or "")
    assert done.stop_reason == STOP_END_TURN


def test_stream_call_one_valid_and_one_malformed_drops_all_tool_calls() -> None:
    """All-or-nothing: if any call is malformed, ProviderResponse.tool_calls == []."""
    client = _FakeOpenAIClient([
        _chunk(tool_calls=[
            _tool_delta(index=0, id="call_1", name="read_file",
                        arguments='{"path":"ok.py"}'),
            _tool_delta(index=1, id="call_2", name="write_file",
                        arguments="{not: valid"),
        ], finish_reason="tool_calls"),
    ])
    provider = OpenAIProvider(model="m", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    assert done.tool_calls == []
    assert done.stop_reason == STOP_END_TURN
    text = done.text or ""
    assert "could not be parsed" in text
    assert "write_file" in text
    assert "{not: valid" not in text


def test_stream_call_done_payload_does_not_contain_raw_secret_arguments() -> None:
    """The controlled error must not echo the raw broken JSON back to the user."""
    client = _FakeOpenAIClient([
        _chunk(tool_calls=[
            _tool_delta(index=0, id="call_1", name="write_file",
                        arguments='{"key":"sk-not-leaked-into-output", malformed'),
        ], finish_reason="tool_calls"),
    ])
    provider = OpenAIProvider(model="m", client=client)

    events = list(provider.stream_call(system="", messages=[], tools=[]))

    done = events[-1].response
    assert done is not None
    text = done.text or ""
    assert "sk-not-leaked-into-output" not in text
