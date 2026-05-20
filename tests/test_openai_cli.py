"""Tests for the non-interactive OpenAI-compatible CLI.

The provider is faked so these tests never make network calls.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from simple_coding_agent import openai_cli
from simple_coding_agent.models import ToolCall
from simple_coding_agent.provider import (
    MockProvider,
    ProviderResponse,
    ProviderStreamEvent,
    TokenUsage,
)


class _FakeOpenAIProvider(MockProvider):
    instances: list[_FakeOpenAIProvider] = []

    def __init__(
        self,
        model: str,
        max_tokens: int,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.base_url = base_url
        self.calls_seen: list[dict[str, Any]] = []
        _FakeOpenAIProvider.instances.append(self)
        super().__init__([MockProvider.direct_answer("fake final answer")])

    def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        self.calls_seen.append({"system": system, "messages": messages, "tools": tools})
        return super().call(system, messages, tools)


class _FakeToolOpenAIProvider(_FakeOpenAIProvider):
    def __init__(
        self,
        model: str,
        max_tokens: int,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(model, max_tokens, api_key, base_url)
        self._script = [
            ProviderResponse(
                text=None,
                tool_calls=[ToolCall(id="tu_1", name="list_files", input={})],
                usage=TokenUsage(),
                stop_reason="tool_use",
            ),
            MockProvider.direct_answer("listed files"),
        ]


class _FakeStreamingOpenAIProvider(_FakeOpenAIProvider):
    def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        self.calls_seen.append({"system": system, "messages": messages, "tools": tools})
        return MockProvider.direct_answer("non-stream answer")

    def stream_call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Iterator[ProviderStreamEvent]:
        self.calls_seen.append({"system": system, "messages": messages, "tools": tools})
        yield ProviderStreamEvent.text_delta("streamed ")
        yield ProviderStreamEvent.text_delta("answer")
        yield ProviderStreamEvent.done(MockProvider.direct_answer("streamed answer"))


@pytest.fixture(autouse=True)
def _clear_provider_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeOpenAIProvider.instances = []
    monkeypatch.delenv("SIMPLE_AGENT_MODEL", raising=False)
    monkeypatch.delenv("SIMPLE_AGENT_MAX_TOKENS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


def test_openai_cli_runs_one_task_with_explicit_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    rc = openai_cli.main([
        "--no-dotenv",
        "--workspace",
        str(tmp_path),
        "--model",
        "test-model",
        "read",
        "README",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert "fake final answer" in captured.out
    assert "Status: completed" in captured.out
    assert _FakeOpenAIProvider.instances[0].model == "test-model"
    assert _FakeOpenAIProvider.instances[0].calls_seen[0]["messages"][0]["content"] == "read README"


def test_openai_cli_streams_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeStreamingOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    rc = openai_cli.main([
        "--no-dotenv",
        "--workspace",
        str(tmp_path),
        "--model",
        "test-model",
        "stream",
        "please",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert "streamed answer" in captured.out
    assert "non-stream answer" not in captured.out


def test_openai_cli_no_stream_uses_non_stream_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeStreamingOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    rc = openai_cli.main([
        "--no-dotenv",
        "--no-stream",
        "--workspace",
        str(tmp_path),
        "--model",
        "test-model",
        "wait",
        "please",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert "non-stream answer" in captured.out


def test_openai_cli_loads_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "\n".join([
            "SIMPLE_AGENT_MODEL=qwen3.6-plus",
            "SIMPLE_AGENT_MAX_TOKENS=321",
            "DASHSCOPE_API_KEY=sk-test",
            "OPENAI_BASE_URL=https://dashscope.example/v1",
        ]),
        encoding="utf-8",
    )

    rc = openai_cli.main([
        "--env-file",
        str(env_file),
        "--workspace",
        str(tmp_path),
        "summarize",
        "files",
    ])

    captured = capsys.readouterr()
    provider = _FakeOpenAIProvider.instances[0]
    assert rc == 0
    assert "qwen3.6-plus" in captured.out
    assert provider.model == "qwen3.6-plus"
    assert provider.max_tokens == 321
    assert provider.api_key == "sk-test"
    assert provider.base_url == "https://dashscope.example/v1"


def test_openai_cli_reports_missing_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    rc = openai_cli.main([
        "--no-dotenv",
        "--workspace",
        str(tmp_path),
        "do",
        "work",
    ])

    captured = capsys.readouterr()
    assert rc == 2
    assert "SIMPLE_AGENT_MODEL" in captured.err


def test_openai_cli_reports_missing_api_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = openai_cli.main([
        "--no-dotenv",
        "--workspace",
        str(tmp_path),
        "--model",
        "test-model",
        "do",
        "work",
    ])

    captured = capsys.readouterr()
    assert rc == 2
    assert "OPENAI_API_KEY" in captured.err


def test_openai_cli_reports_bad_workspace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    rc = openai_cli.main([
        "--no-dotenv",
        "--workspace",
        "/definitely/not/a/workspace",
        "--model",
        "test-model",
        "do",
        "work",
    ])

    captured = capsys.readouterr()
    assert rc == 2
    assert "workspace does not exist" in captured.err


def test_openai_cli_show_steps_prints_tool_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeToolOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    rc = openai_cli.main([
        "--no-dotenv",
        "--workspace",
        str(tmp_path),
        "--model",
        "test-model",
        "--show-steps",
        "list",
        "files",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Tool: list_files" in captured.err
    assert "README.md" in captured.err
    assert "listed files" in captured.out
