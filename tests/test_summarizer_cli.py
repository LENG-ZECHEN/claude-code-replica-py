"""Tests for the ``--summarizer`` CLI flag plumbing.

Covers the three-mode precedence (``auto`` / ``rule`` / ``llm``) wired through
``cli._build_repl_loop`` and the corresponding ``simple-agent --repl`` argparse
surface. The unit-level summarizer behaviour (LLMSummarizer / RuleBasedSummarizer
fall-back rules, tag parsing, truncation) is already covered in
``test_compact.py``; this file proves the CLI flag actually selects the right
implementation and surfaces the expected errors when the choice is impossible.

All tests use MockProvider for determinism — no real provider, no API key.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

import simple_coding_agent.claude_md as cm
import simple_coding_agent.cli as cli_mod
from simple_coding_agent import openai_cli
from simple_coding_agent.cli import main
from simple_coding_agent.compact import LLMSummarizer, RuleBasedSummarizer
from simple_coding_agent.provider import MockProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Never touch ~/.claude/CLAUDE.md during these tests."""
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


def _set_stdin(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    buffer = "\n".join(lines)
    if buffer and not buffer.endswith("\n"):
        buffer = buffer + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(buffer))


def _captured_loops() -> list[Any]:
    return list(getattr(cli_mod, "_LAST_LOOPS", []))


class _FakeOpenAIProvider(MockProvider):
    """Mimics OpenAIProvider's constructor so we can stand in without a network."""

    def __init__(
        self,
        model: str,
        max_tokens: int,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        super().__init__(
            [MockProvider.direct_answer(f"reply {n}") for n in range(50)]
        )


# ---------------------------------------------------------------------------
# Direct _build_repl_loop tests (programmatic surface)
# ---------------------------------------------------------------------------


def test_summarizer_default_auto_no_provider_uses_rule_based(tmp_path: Path) -> None:
    """``auto`` mode with no real provider (MockProvider fallback) → RuleBased."""
    loop = cli_mod._build_repl_loop(tmp_path)
    # `_build_repl_loop` was not given a `provider` argument, so the
    # compactor should fall through to RuleBasedSummarizer even though
    # the loop itself runs against a MockProvider.
    assert isinstance(loop._compactor.summarizer, RuleBasedSummarizer)


def test_summarizer_rule_mode_forces_rule_based_even_with_provider(
    tmp_path: Path,
) -> None:
    """``rule`` mode forces RuleBasedSummarizer regardless of injected provider."""
    real_provider = MockProvider([MockProvider.direct_answer("ok")])
    loop = cli_mod._build_repl_loop(
        tmp_path, provider=real_provider, summarizer_mode="rule",
    )
    assert isinstance(loop._compactor.summarizer, RuleBasedSummarizer)


def test_summarizer_llm_mode_with_provider_uses_llm_summarizer(
    tmp_path: Path,
) -> None:
    """``llm`` mode + a real provider arg → LLMSummarizer wraps that provider."""
    real_provider = MockProvider([MockProvider.direct_answer("ok")])
    loop = cli_mod._build_repl_loop(
        tmp_path, provider=real_provider, summarizer_mode="llm",
    )
    assert isinstance(loop._compactor.summarizer, LLMSummarizer)
    # The LLMSummarizer must use THIS provider instance (no surprise re-wrapping).
    assert loop._compactor.summarizer.provider is real_provider


def test_summarizer_auto_mode_with_provider_uses_llm_summarizer(
    tmp_path: Path,
) -> None:
    """``auto`` mode + a real provider → LLMSummarizer (PDF §4 LLM-based default)."""
    real_provider = MockProvider([MockProvider.direct_answer("ok")])
    loop = cli_mod._build_repl_loop(
        tmp_path, provider=real_provider, summarizer_mode="auto",
    )
    assert isinstance(loop._compactor.summarizer, LLMSummarizer)
    assert loop._compactor.summarizer.provider is real_provider


def test_summarizer_llm_mode_without_provider_raises_system_exit(
    tmp_path: Path,
) -> None:
    """``llm`` mode is impossible without a real provider → clean SystemExit."""
    with pytest.raises(SystemExit) as excinfo:
        cli_mod._build_repl_loop(tmp_path, summarizer_mode="llm")
    assert "real provider" in str(excinfo.value)


def test_summarizer_invalid_mode_raises_value_error(tmp_path: Path) -> None:
    """Programmatic callers passing a bad mode get a typed ValueError."""
    with pytest.raises(ValueError) as excinfo:
        cli_mod._build_repl_loop(tmp_path, summarizer_mode="bogus")
    msg = str(excinfo.value)
    assert "'auto', 'rule', 'llm'" in msg


# ---------------------------------------------------------------------------
# End-to-end CLI tests via main() — argparse + dispatch
# ---------------------------------------------------------------------------


def test_main_summarizer_rule_flag_forces_rule_based(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """``simple-agent --repl --summarizer rule`` exits cleanly and wires RuleBased."""
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl", "--workspace", str(tmp_path), "--summarizer", "rule",
    ])
    assert rc == 0
    loop = _captured_loops()[0]
    assert isinstance(loop._compactor.summarizer, RuleBasedSummarizer)


def test_main_summarizer_default_is_auto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Omitting ``--summarizer`` defaults to ``auto``; MockProvider → RuleBased."""
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl", "--workspace", str(tmp_path),
    ])
    assert rc == 0
    loop = _captured_loops()[0]
    # simple-agent --repl uses MockProvider (no `provider=` injection),
    # so summarizer_mode="auto" should leave the compactor on RuleBased.
    assert isinstance(loop._compactor.summarizer, RuleBasedSummarizer)


def test_main_summarizer_llm_without_real_provider_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--summarizer llm`` without a real provider must NOT silently fall back."""
    _set_stdin(monkeypatch, "/exit")
    # simple-agent --repl has no real provider, so --summarizer llm must
    # raise SystemExit (caught by main()'s caller).
    with pytest.raises(SystemExit):
        main([
            "--repl", "--workspace", str(tmp_path), "--summarizer", "llm",
        ])


def test_main_summarizer_rejects_bad_choice_via_argparse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """argparse rejects an out-of-choices value before we ever build a loop."""
    _set_stdin(monkeypatch, "/exit")
    with pytest.raises(SystemExit) as excinfo:
        main([
            "--repl", "--workspace", str(tmp_path), "--summarizer", "wat",
        ])
    # argparse uses exit code 2 for usage errors.
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# openai_cli --summarizer wiring (mirror coverage)
# ---------------------------------------------------------------------------


def test_openai_cli_summarizer_auto_uses_llm_with_real_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """In openai_cli REPL, ``--summarizer auto`` reuses the OpenAIProvider for LLM
    summarization (PDF §4 LLM-based default)."""
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--repl",
        "--workspace", str(tmp_path),
        "-m", "gpt-test",
        "--no-dotenv",
    ])
    assert rc == 0
    loop = _captured_loops()[0]
    assert isinstance(loop._compactor.summarizer, LLMSummarizer)
    # The LLMSummarizer reuses THIS OpenAIProvider instance — same API key,
    # base URL, model — rather than wrapping a fresh one.
    assert loop._compactor.summarizer.provider is loop._provider


def test_openai_cli_summarizer_rule_forces_rule_based(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """openai_cli ``--summarizer rule`` forces RuleBased (no extra API spend)."""
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--repl",
        "--workspace", str(tmp_path),
        "-m", "gpt-test",
        "--no-dotenv",
        "--summarizer", "rule",
    ])
    assert rc == 0
    loop = _captured_loops()[0]
    assert isinstance(loop._compactor.summarizer, RuleBasedSummarizer)
