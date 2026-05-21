"""M4-D3: ``simple-agent --resume <name>`` CLI flag.

The plan's exit gate is: kill a REPL mid-session, restart with
``--resume <name>``, and verify the prior ``CompactSummary`` reaches the
next system prompt. These four cases formalise that gate, plus the two
clear-failure paths: missing file and corrupted JSON.
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
from simple_coding_agent.session_store import save_session
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


@pytest.fixture
def sessions_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> Path:
    d = tmp_path / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(d))
    return d


def _set_stdin(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    buffer = "\n".join(lines)
    if buffer and not buffer.endswith("\n"):
        buffer = buffer + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(buffer))


def _seed_saved_session_with_summary(
    sessions_dir: Path, name: str,
) -> CompactSummary:
    """Plant a session file on disk so ``--resume`` has something to load."""
    summary = CompactSummary(
        boundary_uuid="b-1",
        summary_text="restored summary text body for the resume test",
        messages_summarized=4,
        pre_token_count=8_000,
        post_token_count=1_200,
        restored_files=[],
        timestamp="2026-05-21T01:23:45+00:00",
    )
    save_session(
        sessions_dir / f"{name}.json",
        transcript=Transcript(),
        last_summary=summary,
    )
    return summary


# ---------------------------------------------------------------------------
# 1. Resume continues with the saved compact summary
# ---------------------------------------------------------------------------


def test_resume_continues_with_saved_compact_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
) -> None:
    saved_summary = _seed_saved_session_with_summary(sessions_dir, "alpha")

    captured: dict[str, MockProvider] = {}

    def _provider_factory(_ws: Path) -> Any:
        p = MockProvider([MockProvider.direct_answer("resumed reply")])
        captured["p"] = p
        return p

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)
    _set_stdin(monkeypatch, "post-resume question", "/exit")
    rc = main([
        "--repl",
        "--resume", "alpha",
        "--workspace", str(tmp_path),
    ])
    assert rc == 0

    systems = [c.system for c in captured["p"].history]
    assert systems, "the resumed loop should have issued at least one provider call"
    assert any(saved_summary.summary_text in s for s in systems)
    assert any("## Conversation Summary" in s for s in systems)


# ---------------------------------------------------------------------------
# 2. Missing session -> clear error, nonzero exit
# ---------------------------------------------------------------------------


def test_resume_missing_session_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--resume", "does_not_exist",
        "--workspace", str(tmp_path),
    ])
    captured = capsys.readouterr()
    combined = captured.out + captured.err

    assert rc != 0
    assert (
        "no such session" in combined.lower()
        or "not found" in combined.lower()
    )


# ---------------------------------------------------------------------------
# 3. Corrupted session JSON does not crash the process
# ---------------------------------------------------------------------------


def test_resume_corrupted_session_does_not_crash_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (sessions_dir / "broken.json").write_text(
        "{this is not valid json", encoding="utf-8",
    )
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--resume", "broken",
        "--workspace", str(tmp_path),
    ])
    captured = capsys.readouterr()
    combined = captured.out + captured.err

    # Process must not raise. It either prints a warning and continues, or
    # exits nonzero with a clear message; either is acceptable.
    assert rc != 0 or "could not load session" in combined.lower()


# ---------------------------------------------------------------------------
# 4. Save → resume yields the identical next system prompt
# ---------------------------------------------------------------------------


def test_save_then_resume_produces_identical_next_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sessions_dir: Path,
) -> None:
    big_text = "x " * 5_000
    answers_a = [
        MockProvider.direct_answer(big_text + f" turn {n}") for n in range(15)
    ]
    captured_a: dict[str, MockProvider] = {}

    def _provider_a(_ws: Path) -> Any:
        p = MockProvider(answers_a)
        captured_a["p"] = p
        return p

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_a)
    _set_stdin(
        monkeypatch,
        *([f"turn {n}: " + big_text for n in range(15)]
          + ["/save resume_target", "/exit"]),
    )
    rc_a = main([
        "--repl",
        "--workspace", str(tmp_path / "a"),
        "--max-context-tokens", "5000",
        "--reserved-output-tokens", "1000",
    ])
    assert rc_a == 0

    saved = sessions_dir / "resume_target.json"
    payload = json.loads(saved.read_text(encoding="utf-8"))
    assert payload["last_summary"] is not None
    expected_summary = payload["last_summary"]["summary_text"]

    captured_b: dict[str, MockProvider] = {}

    def _provider_b(_ws: Path) -> Any:
        p = MockProvider([MockProvider.direct_answer("resumed turn reply")])
        captured_b["p"] = p
        return p

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_b)
    _set_stdin(monkeypatch, "first turn after resume", "/exit")
    rc_b = main([
        "--repl",
        "--resume", "resume_target",
        "--workspace", str(tmp_path / "b"),
    ])
    assert rc_b == 0

    systems = [c.system for c in captured_b["p"].history]
    assert systems, "resumed REPL should have issued one provider call"
    assert any(expected_summary in s for s in systems)
