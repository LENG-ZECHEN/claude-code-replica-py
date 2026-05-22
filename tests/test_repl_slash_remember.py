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


# ---------------------------------------------------------------------------
# Patch 5 (Cap2): /remember-session writes to SessionMemory.
# ---------------------------------------------------------------------------


def test_remember_session_writes_to_session_memory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Direct ``_handle_slash_command`` invocation appends to session memory."""
    from simple_coding_agent.cli import _handle_slash_command
    from simple_coding_agent.memory import SessionMemory

    session_memory = SessionMemory()

    class _StubLoop:
        def __init__(self) -> None:
            self._session_memory = session_memory
            self._project_memory = None

    loop = _StubLoop()
    signal = _handle_slash_command(
        "/remember-session hello world", loop,  # type: ignore[arg-type]
    )

    assert signal == "continue"
    entries = session_memory.all()
    assert len(entries) == 1
    assert entries[0].body == "hello world"
    out = capsys.readouterr().out
    assert "Remembered session note" in out


def test_remember_session_rejects_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bearer-token bodies are rejected; no entry is added."""
    from simple_coding_agent.cli import _handle_slash_command
    from simple_coding_agent.memory import SessionMemory

    session_memory = SessionMemory()

    class _StubLoop:
        def __init__(self) -> None:
            self._session_memory = session_memory
            self._project_memory = None

    loop = _StubLoop()
    signal = _handle_slash_command(
        "/remember-session Authorization: Bearer abc.def.ghi.jkl_mn",
        loop,  # type: ignore[arg-type]
    )

    assert signal == "continue"
    assert session_memory.all() == []
    out = capsys.readouterr().out
    assert "Could not save session memory" in out
    assert "secret" in out.lower()


def test_remember_session_usage_when_args_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No body text -> one-line usage hint, no entry added."""
    from simple_coding_agent.cli import _handle_slash_command
    from simple_coding_agent.memory import SessionMemory

    session_memory = SessionMemory()

    class _StubLoop:
        def __init__(self) -> None:
            self._session_memory = session_memory
            self._project_memory = None

    loop = _StubLoop()
    _handle_slash_command("/remember-session", loop)  # type: ignore[arg-type]

    out = capsys.readouterr().out
    assert "Usage: /remember-session" in out
    assert session_memory.all() == []


def test_remember_session_help_lists_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``/help`` advertises ``/remember-session`` so users discover it."""
    _set_stdin(monkeypatch, "/help", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "/remember-session" in out


def test_remember_session_injected_in_next_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    memory_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After ``/remember-session`` the new note is visible via to_snippets."""
    from simple_coding_agent.cli import (
        _build_repl_loop,
        _handle_slash_command,
    )
    from simple_coding_agent.memory import SessionMemory

    session_memory = SessionMemory()
    loop = _build_repl_loop(
        tmp_path,
        max_steps=1,
        max_context_tokens=200_000,
        reserved_output_tokens=8_192,
        session_memory=session_memory,
    )
    _handle_slash_command(
        "/remember-session please prefer tabs over spaces", loop,
    )

    snippets = session_memory.to_snippets()
    assert any("prefer tabs over spaces" in s for s in snippets)


def test_remember_session_persists_across_dump_and_load(
    tmp_path: Path,
) -> None:
    """``dump_json`` + ``load_json`` round-trip preserves a session note."""
    from simple_coding_agent.cli import _handle_slash_command
    from simple_coding_agent.memory import SessionMemory

    session_memory = SessionMemory()

    class _StubLoop:
        def __init__(self) -> None:
            self._session_memory = session_memory
            self._project_memory = None

    loop = _StubLoop()
    _handle_slash_command(
        "/remember-session keep going after lunch",
        loop,  # type: ignore[arg-type]
    )

    path = tmp_path / "session_memory.json"
    session_memory.dump_json(path)
    reloaded = SessionMemory.load_json(path)

    bodies = [e.body for e in reloaded.all()]
    assert "keep going after lunch" in bodies
