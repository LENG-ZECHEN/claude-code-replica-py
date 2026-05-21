"""M1-A1/A3/A4: REPL tests — written before implementation (TDD).

Covers Section 3.1 of RUNTIME_ACTIVATION_PLAN.md:
 - `--repl` flag dispatches into a REPL handler that shares one AgentLoop
   across user inputs.
 - Slash commands: `/exit` (and `/quit`), `/help`, unknown-command hint.
 - EOF on stdin, KeyboardInterrupt during a turn, empty input.
 - `--max-steps`, `--max-context-tokens`, `--reserved-output-tokens` flag
   propagation into the AgentLoop / ContextBudget.

All cases use MockProvider for determinism — no real provider, no API key,
no real shell, no real user CLAUDE.md (loader is monkeypatched).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

import simple_coding_agent.claude_md as cm
import simple_coding_agent.cli as cli_mod
from simple_coding_agent.cli import main
from simple_coding_agent.coding_tools import WorkspaceBoundaryError
from simple_coding_agent.context import ContextBudget
from simple_coding_agent.provider import MockProvider, ProviderResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_user_claude_md(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Never touch ~/.claude/CLAUDE.md during REPL tests."""
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


def _captured_loops() -> list[Any]:
    """Snapshot of AgentLoop instances that the REPL constructed.

    The REPL records each loop it created on cli._LAST_LOOPS so tests can
    inspect token budget / max_steps without monkeypatching constructors.
    """
    return list(getattr(cli_mod, "_LAST_LOOPS", []))


def _set_stdin(
    monkeypatch: pytest.MonkeyPatch, *lines: str,
) -> None:
    """Wire stdin so REPL reads the given lines in order (then hits EOF)."""
    buffer = "\n".join(lines)
    if buffer and not buffer.endswith("\n"):
        buffer = buffer + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(buffer))


def _scripted_provider_factory(
    *responses: ProviderResponse,
) -> MockProvider:
    """Build a single MockProvider preloaded with end_turn responses."""
    script = list(responses) or [MockProvider.direct_answer("ok")]
    return MockProvider(script)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_repl_carries_transcript_across_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange: two user inputs in one REPL session.
    _set_stdin(monkeypatch, "first question", "second question", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])

    captured = capsys.readouterr()
    loops = _captured_loops()

    # Assert: same loop carries both inputs in its transcript.
    assert rc == 0, captured.out + captured.err
    assert len(loops) == 1
    transcript_msgs = loops[0]._transcript.all_messages()
    user_texts = [m.content for m in transcript_msgs if m.role.value == "user"
                  and isinstance(m.content, str)]
    assert "first question" in user_texts
    assert "second question" in user_texts


def test_repl_exit_command_returns_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0


def test_repl_quit_alias_works(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/quit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0


def test_repl_help_lists_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/help", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "/exit" in out
    assert "/help" in out
    assert "/stats" in out


def test_repl_stats_prints_metric_counters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`/stats` prints every per-mechanism counter line so the exit gate is met."""
    _set_stdin(monkeypatch, "hello there", "/stats", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "full compacts" in out
    assert "reactive compacts" in out
    assert "microcompact runs" in out
    assert "snip runs" in out
    assert "externalized bytes" in out
    assert "turns recorded:" in out


def test_repl_stats_increments_after_each_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`tokens_per_turn` accumulates inside the shared loop across REPL turns."""
    _set_stdin(monkeypatch, "alpha", "beta", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])

    captured = capsys.readouterr()
    loops = _captured_loops()

    assert rc == 0, captured.out + captured.err
    assert len(loops) == 1
    metrics = loops[0]._metrics
    assert len(metrics.tokens_per_turn) == 2


def test_repl_unknown_slash_command_prints_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/foo", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "unknown command" in out.lower()
    assert "/help" in out


def test_repl_keyboardinterrupt_does_not_drop_transcript(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    # Arrange: turn 1 succeeds; turn 2 raises KeyboardInterrupt mid-turn;
    # turn 3 succeeds. After the interrupt the REPL must still have the
    # turn-1 user message and be able to process turn 3.
    import simple_coding_agent.loop as loop_mod

    real_run = loop_mod.AgentLoop.run
    call_count = {"n": 0}

    def _flaky_run(self: Any, user_input: str) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise KeyboardInterrupt
        return real_run(self, user_input)

    monkeypatch.setattr(loop_mod.AgentLoop, "run", _flaky_run)
    _set_stdin(
        monkeypatch,
        "first ok turn",
        "interrupted turn",
        "third ok turn",
        "/exit",
    )
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0

    loops = _captured_loops()
    msgs = loops[0]._transcript.all_messages()
    user_texts = [m.content for m in msgs if m.role.value == "user"
                  and isinstance(m.content, str)]
    # Surviving turns must still be in the transcript.
    assert "first ok turn" in user_texts
    assert "third ok turn" in user_texts


def test_repl_empty_input_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "", "   ", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = _captured_loops()
    # Empty inputs do not trigger provider calls -> transcript has zero user msgs.
    msgs = loops[0]._transcript.all_messages()
    user_strings = [m for m in msgs if m.role.value == "user"
                    and isinstance(m.content, str)]
    assert user_strings == []


def test_repl_with_max_steps_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--max-steps", "50", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = _captured_loops()
    assert loops[0]._max_steps == 50


def test_repl_passes_workspace_to_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = _captured_loops()

    read_tool = loops[0]._tool_executor._registry.get("read_file")
    with pytest.raises(WorkspaceBoundaryError):
        read_tool.fn(path="../../etc/passwd")


def test_repl_long_conversation_triggers_compact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    # Arrange: a tiny context budget forces ContextCompactor.should_compact()
    # to fire on the second turn.
    big_text = "x " * 5_000  # ~10 000 chars -> ~2500 tokens by the char/4 heuristic
    answers = [
        MockProvider.direct_answer(big_text + f" turn {n}") for n in range(20)
    ]

    def _provider_factory(_workspace: Path) -> Any:
        return MockProvider(answers)

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)

    inputs = [f"turn {n}: " + big_text for n in range(20)] + ["/exit"]
    _set_stdin(monkeypatch, *inputs)

    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "5000",
        "--reserved-output-tokens", "1000",
    ])
    assert rc == 0

    loops = _captured_loops()
    # Compaction must have run at least once during the session.
    assert loops[0]._last_summary is not None


def test_repl_compact_summary_appears_in_next_system_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    big_text = "y " * 5_000
    answers = [
        MockProvider.direct_answer(big_text + f" turn {n}") for n in range(20)
    ]
    captured_provider: dict[str, MockProvider] = {}

    def _provider_factory(_workspace: Path) -> Any:
        p = MockProvider(answers)
        captured_provider["p"] = p
        return p

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)

    inputs = [f"turn {n}: " + big_text for n in range(20)] + ["/exit"]
    _set_stdin(monkeypatch, *inputs)

    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "5000",
        "--reserved-output-tokens", "1000",
    ])
    assert rc == 0

    systems = [c.system for c in captured_provider["p"].history]
    assert any("## Conversation Summary" in s for s in systems)


def test_repl_stdin_eof_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    # No newline, no /exit -> reading hits EOF immediately.
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0


def test_repl_streams_text_when_stream_flag_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    answers = [MockProvider.direct_answer("hello-stream-token")]

    def _provider_factory(_workspace: Path) -> Any:
        return MockProvider(answers)

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)
    _set_stdin(monkeypatch, "hi", "/exit")
    rc = main(["--repl", "--stream", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hello-stream-token" in out


def test_repl_max_context_tokens_flag_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "5000",
    ])
    assert rc == 0
    loops = _captured_loops()
    assert isinstance(loops[0]._budget, ContextBudget)
    assert loops[0]._budget.max_tokens == 5000


def test_repl_reserved_output_tokens_flag_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "8000",
        "--reserved-output-tokens", "1234",
    ])
    assert rc == 0
    loops = _captured_loops()
    assert loops[0]._budget.reserved_output_tokens == 1234
