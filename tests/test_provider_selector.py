"""Tests for Provider.call_selector — MockProvider and OpenAIProvider."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from simple_coding_agent.provider import MockProvider, OpenAIProvider, SelectorError

# ---------------------------------------------------------------------------
# MockProvider.call_selector
# ---------------------------------------------------------------------------

def test_mock_provider_call_selector_returns_scripted_response() -> None:
    provider = MockProvider(
        script=[],
        selector_responses=[{"selected_memories": ["a.md"]}],
    )
    result = provider.call_selector(
        system="sys",
        user="what is the user's role?",
        output_schema={"required": ["selected_memories"]},
    )
    assert result == {"selected_memories": ["a.md"]}


def test_mock_provider_selector_sequential_across_calls() -> None:
    provider = MockProvider(
        script=[],
        selector_responses=[
            {"selected_memories": ["a.md"]},
            {"selected_memories": ["b.md"]},
        ],
    )
    r1 = provider.call_selector(system="s", user="q1", output_schema={})
    r2 = provider.call_selector(system="s", user="q2", output_schema={})
    assert r1 == {"selected_memories": ["a.md"]}
    assert r2 == {"selected_memories": ["b.md"]}


def test_mock_provider_selector_raises_when_exhausted() -> None:
    provider = MockProvider(script=[], selector_responses=[])
    with pytest.raises(SelectorError):
        provider.call_selector(system="s", user="q", output_schema={})


def test_mock_provider_selector_independent_from_main_responses() -> None:
    from simple_coding_agent.provider import ProviderResponse, TokenUsage
    main_response = ProviderResponse(
        text="hello", tool_calls=[], usage=TokenUsage(), stop_reason="end_turn"
    )
    provider = MockProvider(
        script=[main_response],
        selector_responses=[{"selected_memories": []}],
    )
    # call_selector should not advance the main script index
    provider.call_selector(system="s", user="q", output_schema={})
    result = provider.call(system="s", messages=[], tools=[])
    assert result.text == "hello"


# ---------------------------------------------------------------------------
# OpenAIProvider.call_selector
# ---------------------------------------------------------------------------

def test_openai_provider_selector_parses_json() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(message=MagicMock(content='{"selected_memories": ["a.md"]}'))
        ]
    )
    provider = OpenAIProvider(model="gpt-4o", client=mock_client, selector_model="gpt-4o-mini")
    result = provider.call_selector(
        system="sys",
        user="user query",
        output_schema={"required": ["selected_memories"]},
    )
    assert result == {"selected_memories": ["a.md"]}
    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["max_tokens"] == 256


def test_openai_provider_selector_raises_on_malformed_json() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="not valid json at all"))]
    )
    provider = OpenAIProvider(model="gpt-4o", client=mock_client)
    with pytest.raises(SelectorError, match="malformed JSON"):
        provider.call_selector(system="s", user="u", output_schema={})


def test_openai_provider_selector_raises_on_api_error() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("network timeout")
    provider = OpenAIProvider(model="gpt-4o", client=mock_client)
    with pytest.raises(SelectorError):
        provider.call_selector(system="s", user="u", output_schema={})


def test_openai_provider_selector_raises_on_schema_mismatch() -> None:
    mock_client = MagicMock()
    # Returns JSON that is missing the required key
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"wrong_key": []}'))]
    )
    provider = OpenAIProvider(model="gpt-4o", client=mock_client)
    with pytest.raises(SelectorError, match="schema mismatch"):
        provider.call_selector(
            system="s",
            user="u",
            output_schema={"required": ["selected_memories"]},
        )
