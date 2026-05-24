"""P9-M5 / A2: ``simple-agent-openai --repl`` REPL backed by the real provider.

These tests substitute a fake OpenAIProvider so no network is involved.
They prove the wiring is correct: the REPL constructs an ``AgentLoop``
with the OpenAI provider class, drives one user turn through the
shared ``_drive_repl_session`` helper, honours slash commands, and
returns 0 on ``/exit``. The auto-learn cue + ``/remember`` plumbing is
also live in this REPL since it shares the cli helpers.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

import simple_coding_agent.claude_md as cm
from simple_coding_agent import cli as cli_mod
from simple_coding_agent import openai_cli
from simple_coding_agent.provider import MockProvider


class _FakeOpenAIProvider(MockProvider):
    """A MockProvider that mimics OpenAIProvider's constructor signature."""

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
        _FakeOpenAIProvider.instances.append(self)
        super().__init__(
            [MockProvider.direct_answer(f"openai-repl reply {n}") for n in range(50)]
        )


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


@pytest.fixture(autouse=True)
def _clear_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeOpenAIProvider.instances = []
    monkeypatch.delenv("SIMPLE_AGENT_MODEL", raising=False)
    monkeypatch.delenv("SIMPLE_AGENT_MAX_TOKENS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


@pytest.fixture
def memory_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    d = tmp_path / "project-memory"
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(d))
    return d


def _set_stdin(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    buffer = "\n".join(lines)
    if buffer and not buffer.endswith("\n"):
        buffer = buffer + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(buffer))


def _captured_loops() -> list[Any]:
    return list(getattr(cli_mod, "_LAST_LOOPS", []))


def test_openai_repl_flag_dispatches_to_repl_handler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    captured = capsys.readouterr()

    assert rc == 0, captured.out + captured.err
    assert "simple-agent-openai REPL" in captured.out


def test_openai_repl_carries_transcript_across_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin(monkeypatch, "first", "second", "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    captured = capsys.readouterr()
    loops = _captured_loops()

    assert rc == 0, captured.out + captured.err
    assert len(loops) == 1
    msgs = loops[0]._transcript.all_messages()
    user_texts = [m.content for m in msgs if m.role.value == "user"
                  and isinstance(m.content, str)]
    assert "first" in user_texts
    assert "second" in user_texts


def test_openai_repl_uses_real_provider_class(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    _set_stdin(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "the-model",
        "--max-tokens", "777",
    ])
    assert rc == 0
    provider = _FakeOpenAIProvider.instances[0]
    assert provider.model == "the-model"
    assert provider.max_tokens == 777
    assert provider.api_key == "sk-test"
    assert provider.base_url == "https://example.test/v1"


def test_openai_repl_help_lists_remember_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin(monkeypatch, "/help", "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "/remember" in out
    assert "/exit" in out


def test_openai_repl_remember_writes_through_project_memory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin(
        monkeypatch,
        "/remember feedback indent_pref user prefers 4-space indentation",
        "/exit",
    )

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    saved = memory_dir / "indent_pref.md"
    assert saved.exists(), out
    from simple_coding_agent.memory import ProjectMemory
    entry = ProjectMemory(storage_dir=str(memory_dir)).load("indent_pref")
    assert entry is not None
    assert entry.body == "user prefers 4-space indentation"


def test_openai_repl_jizhu_cue_prints_save_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin(monkeypatch, "记住请用 tabs 缩进", "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "cue detected" in out
    assert "记住" in out


def test_openai_repl_one_shot_still_requires_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Backward compat: one-shot mode without --repl still demands a prompt."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    rc = openai_cli.main([
        "--no-dotenv",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    err = capsys.readouterr().err

    assert rc == 2
    assert "Prompt must not be empty" in err


# ---------------------------------------------------------------------------
# M1: --verbose flag also reaches the OpenAI-backed REPL
# ---------------------------------------------------------------------------

def _set_stdin_openai(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    buf = "\n".join(lines)
    if buf and not buf.endswith("\n"):
        buf += "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(buf))


def test_openai_repl_verbose_flag_streams_budget_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--verbose`` in the openai REPL must emit ``[trace] [budget]`` lines."""
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin_openai(monkeypatch, "what is testing", "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--verbose",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "[trace] [budget]" in captured.err


def test_openai_repl_default_no_verbose_is_silent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without ``--verbose``, the openai REPL emits no ``[trace]`` lines."""
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin_openai(monkeypatch, "say hi", "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "[trace]" not in captured.err


# ---------------------------------------------------------------------------
# M2 — --aggressive-thresholds preset (openai_cli surface)
# ---------------------------------------------------------------------------

def test_openai_repl_aggressive_thresholds_wires_preset_into_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``simple-agent-openai --repl --aggressive-thresholds`` lowers every threshold."""
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin_openai(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--aggressive-thresholds",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "[aggressive-thresholds]" in captured.out
    assert "[aggressive-thresholds]" not in captured.err

    loop = _captured_loops()[0]
    preset = cli_mod._AGGRESSIVE_THRESHOLDS
    assert loop._compactor.compact_threshold == preset["compact_threshold"]
    assert loop._snip_tool._keep_recent == preset["snip_keep_recent"]
    assert loop._microcompactor._threshold_minutes == preset["microcompact_minutes"]


def test_openai_repl_aggressive_thresholds_omitted_keeps_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without the flag, the openai REPL does NOT emit the banner."""
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin_openai(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "[aggressive-thresholds]" not in captured.out
    loop = _captured_loops()[0]
    assert loop._compactor.compact_threshold == 0.8
    assert loop._snip_tool._keep_recent == 3


# ---------------------------------------------------------------------------
# M2 — openai_cli sentinel handling must match cli (no drift)
# ---------------------------------------------------------------------------

def test_openai_repl_aggressive_budget_matches_cli_sentinel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """openai_cli honours the preset for the two flag-backed budget fields.

    Regression guard for the M2 bug: ``context_tokens`` /
    ``reserved_output_tokens`` were always shadowed by the argparse
    defaults. Because ``openai_cli`` routes through ``cli._build_repl_loop``
    for threshold resolution, the effective budget here must equal the
    preset values, exactly as the MockProvider REPL does.
    """
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin_openai(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--aggressive-thresholds",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    assert rc == 0, capsys.readouterr().err
    loop = _captured_loops()[0]
    preset = cli_mod._AGGRESSIVE_THRESHOLDS
    assert loop._budget.max_tokens == preset["context_tokens"]
    assert loop._budget.reserved_output_tokens == preset["reserved_output_tokens"]


def test_openai_repl_explicit_budget_overrides_preset_like_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Explicit budget flags win per-field in openai_cli, just like cli.

    Proves the three-state precedence (explicit > preset > default) is the
    same code path for both REPLs: an explicit ``--max-context-tokens`` /
    ``--reserved-output-tokens`` beats the preset while unspecified preset
    fields still apply.
    """
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin_openai(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--aggressive-thresholds",
        "--max-context-tokens", "16000",
        "--reserved-output-tokens", "999",
        "--workspace", str(tmp_path),
        "--model", "test-model",
    ])
    assert rc == 0, capsys.readouterr().err
    loop = _captured_loops()[0]
    assert loop._budget.max_tokens == 16000
    assert loop._budget.reserved_output_tokens == 999
    # An unspecified preset field still applies.
    assert loop._snip_tool._keep_recent == cli_mod._AGGRESSIVE_THRESHOLDS[
        "snip_keep_recent"
    ]


# ---------------------------------------------------------------------------
# M1 (ctx-mgmt-demo): --microcompact-minutes and --max-turns flags
# ---------------------------------------------------------------------------

def test_openai_repl_microcompact_minutes_flag_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``--microcompact-minutes N`` must propagate to the openai REPL's MicroCompactor."""
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _set_stdin(monkeypatch, "/exit")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
        "--microcompact-minutes", "3",
    ])
    assert rc == 0
    loops = _captured_loops()
    assert loops
    assert loops[0]._microcompactor._threshold_minutes == 3


def test_openai_repl_max_turns_exits_after_n_turns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``--max-turns 2`` causes the REPL to exit cleanly after exactly 2 user turns."""
    monkeypatch.setattr(openai_cli, "OpenAIProvider", _FakeOpenAIProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # Provide 5 inputs; max-turns=2 should stop after turn1 + turn2.
    _set_stdin(monkeypatch, "turn1", "turn2", "turn3", "turn4", "turn5")

    rc = openai_cli.main([
        "--no-dotenv",
        "--repl",
        "--workspace", str(tmp_path),
        "--model", "test-model",
        "--max-turns", "2",
    ])
    assert rc == 0
    loops = _captured_loops()
    assert loops
    msgs = loops[0]._transcript.all_messages()
    user_texts = [
        m.content for m in msgs
        if m.role.value == "user" and isinstance(m.content, str)
    ]
    assert "turn1" in user_texts
    assert "turn2" in user_texts
    assert "turn3" not in user_texts
