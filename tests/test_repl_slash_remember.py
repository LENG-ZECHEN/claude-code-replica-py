"""P9-M5 / B2 + B4: REPL ``/remember`` slash command + auto-learn cue.

Covers section 3.2 ``test_repl_slash_commands.py`` cases (B2 enabling for
B4) and the exit-gate behaviour ``"记住" cue triggers save prompt``:

  - ``/remember <type> <id> <body...>`` persists a ``MemoryEntry`` to the
    REPL's ``ProjectMemory``, honouring secret-rejection and unknown-type
    validation.
  - ``/remember`` with too few arguments prints a one-line usage hint.
  - Auto-learn cue scanner prints the format_hint() string BEFORE the
    user turn runs, so the operator sees the save target without
    inspecting code.

All cases use MockProvider for determinism; ``SIMPLE_AGENT_MEMORY_DIR``
points at a tmp dir so test runs never touch real on-disk memory.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import simple_coding_agent.claude_md as cm
from simple_coding_agent.cli import main


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


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


def test_remember_command_adds_to_project_memory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(
        monkeypatch,
        "/remember feedback tabs_pref user prefers tabs over spaces",
        "/exit",
    )
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    saved = memory_dir / "tabs_pref.json"
    assert saved.exists(), out
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert payload["type"] == "feedback"
    assert payload["body"] == "user prefers tabs over spaces"
    assert "Remembered tabs_pref" in out


def test_remember_command_rejects_unknown_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(
        monkeypatch,
        "/remember bogus name1 some body text",
        "/exit",
    )
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Unknown memory type" in out
    assert not list(memory_dir.glob("name1.json"))


def test_remember_command_rejects_secret_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(
        monkeypatch,
        "/remember user oops API_KEY=sk-not-a-real-secret",
        "/exit",
    )
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Could not save memory" in out
    assert "secret" in out.lower()
    assert not (memory_dir / "oops.json").exists()


def test_remember_command_usage_when_args_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/remember", "/remember user only_id", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert out.count("Usage: /remember") == 2


def test_help_lists_remember_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/help", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "/remember" in out


def test_chinese_jizhu_cue_prints_save_prompt_before_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The 'remember' cue in Chinese triggers the format_hint line on stdout."""
    _set_stdin(monkeypatch, "记住我喜欢用 tabs 缩进", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "cue detected" in out
    assert "记住" in out
    assert "/remember" in out


def test_english_prefer_cue_prints_save_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "I prefer dark mode in the editor", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "cue detected" in out
    assert "prefer" in out


def test_neutral_input_does_not_print_cue_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "what is 1 + 1?", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "cue detected" not in out
