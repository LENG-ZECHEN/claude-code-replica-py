"""M4-D2: REPL `/save <name>` and `/load <name>` slash commands.

The Transcript persistence primitives from D1 are exposed through two new
REPL slash commands. ``/save`` writes the full session (transcript +
last_summary) to ``<sessions_dir>/<name>.json``; ``/load`` restores both
into the active ``AgentLoop`` so the next user turn sees the same compact
summary in the system prompt. ``SIMPLE_AGENT_SESSIONS_DIR`` overrides the
default ``~/.simple-agent/sessions/`` directory for test isolation.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

import simple_coding_agent.claude_md as cm
import simple_coding_agent.cli as cli_mod
from simple_coding_agent.cli import main
from simple_coding_agent.models import CompactSummary
from simple_coding_agent.provider import MockProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Never touch ~/.claude/CLAUDE.md during REPL tests."""
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


@pytest.fixture
def sessions_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> Path:
    """Redirect named-session storage to a per-test tmp dir."""
    d = tmp_path / "sessions"
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(d))
    return d


def _set_stdin(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    buffer = "\n".join(lines)
    if buffer and not buffer.endswith("\n"):
        buffer = buffer + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(buffer))


def _captured_loops() -> list[Any]:
    return list(getattr(cli_mod, "_LAST_LOOPS", []))


# ---------------------------------------------------------------------------
# 1. /save writes a session file
# ---------------------------------------------------------------------------


def test_save_creates_session_file_under_configured_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
) -> None:
    _set_stdin(monkeypatch, "hi", "/save mysession", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])

    assert rc == 0
    saved = sessions_dir / "mysession.json"
    assert saved.exists()
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert "transcript" in payload
    assert "last_summary" in payload
    serialized_messages = payload["transcript"]["messages"]
    user_msgs = [
        m for m in serialized_messages
        if m["role"] == "user" and isinstance(m["content"], str)
    ]
    assert any(m["content"] == "hi" for m in user_msgs)


# ---------------------------------------------------------------------------
# 2. /save with no argument prints a usage hint and stays in REPL
# ---------------------------------------------------------------------------


def test_save_with_no_arg_prints_usage_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/save", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "/save <name>" in out


# ---------------------------------------------------------------------------
# 3. /save rejects path-traversal names
# ---------------------------------------------------------------------------


def test_save_rejects_path_traversal_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/save ../escape", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "invalid session name" in out.lower()
    parent_of_sessions = sessions_dir.parent
    assert not (parent_of_sessions / "escape.json").exists()


# ---------------------------------------------------------------------------
# 4. /load restores transcript into the active loop
# ---------------------------------------------------------------------------


def test_load_restores_transcript_into_active_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
) -> None:
    _set_stdin(
        monkeypatch,
        "alpha question",
        "/save alpha_session",
        "/load alpha_session",
        "/exit",
    )
    rc = main(["--repl", "--workspace", str(tmp_path)])

    assert rc == 0
    loop = _captured_loops()[0]
    user_strings = [
        m.content for m in loop._transcript.all_messages()
        if m.role.value == "user" and isinstance(m.content, str)
    ]
    assert "alpha question" in user_strings


# ---------------------------------------------------------------------------
# 5. /load on missing file prints a clear error and stays in REPL
# ---------------------------------------------------------------------------


def test_load_missing_session_prints_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/load nothing_here", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "no such session" in out.lower() or "not found" in out.lower()


# ---------------------------------------------------------------------------
# 6. /load restores CompactSummary so the next system prompt sees it
# ---------------------------------------------------------------------------


def test_load_restores_compact_summary_into_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
) -> None:
    big_text = "y " * 5_000
    answers = [
        MockProvider.direct_answer(big_text + f" turn {n}") for n in range(20)
    ]

    def _provider_factory(_ws: Path) -> Any:
        return MockProvider(answers)

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)

    inputs_a = [f"turn {n}: " + big_text for n in range(20)] + [
        "/save compacted_session",
        "/exit",
    ]
    _set_stdin(monkeypatch, *inputs_a)
    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "5000",
        "--reserved-output-tokens", "1000",
    ])
    assert rc == 0

    saved = sessions_dir / "compacted_session.json"
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert payload["last_summary"] is not None
    assert payload["last_summary"]["summary_text"]

    captured_b: dict[str, MockProvider] = {}
    fresh_answers = [MockProvider.direct_answer("session-B reply")]

    def _fresh_provider(_ws: Path) -> Any:
        p = MockProvider(fresh_answers)
        captured_b["p"] = p
        return p

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _fresh_provider)
    _set_stdin(monkeypatch, "/load compacted_session", "anything", "/exit")
    rc_b = main([
        "--repl",
        "--workspace", str(tmp_path / "fresh"),
    ])
    assert rc_b == 0

    systems = [c.system for c in captured_b["p"].history]
    assert systems, "the loaded session should have driven at least one provider call"
    assert any("## Conversation Summary" in s for s in systems)


# ---------------------------------------------------------------------------
# 7. /help mentions /save and /load
# ---------------------------------------------------------------------------


def test_help_lists_save_and_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/help", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "/save" in out
    assert "/load" in out


# ---------------------------------------------------------------------------
# 8. CompactSummary fields all round-trip through save_session / load_session
# ---------------------------------------------------------------------------


def test_saved_compact_summary_roundtrips_all_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
) -> None:
    from simple_coding_agent.session_store import (
        load_session,
        save_session,
    )
    from simple_coding_agent.transcript import Transcript

    summary = CompactSummary(
        boundary_uuid="b-1",
        summary_text="restored summary text",
        messages_summarized=7,
        pre_token_count=12_000,
        post_token_count=3_500,
        restored_files=["a.py", "b.py"],
        timestamp="2026-05-21T01:23:45+00:00",
    )
    transcript = Transcript()
    path = sessions_dir / "direct.json"
    save_session(path, transcript=transcript, last_summary=summary)

    _t, restored = load_session(path)
    assert restored is not None
    assert restored.boundary_uuid == "b-1"
    assert restored.summary_text == "restored summary text"
    assert restored.messages_summarized == 7
    assert restored.pre_token_count == 12_000
    assert restored.post_token_count == 3_500
    assert restored.restored_files == ["a.py", "b.py"]
    assert restored.timestamp == "2026-05-21T01:23:45+00:00"
