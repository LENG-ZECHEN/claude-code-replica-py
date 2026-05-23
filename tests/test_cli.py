"""Phase 10: CLI smoke test -- proves the MockProvider demo runs cleanly.

Lightweight by design: no network, no LLM, no API key. The CLI uses
``tempfile.TemporaryDirectory`` so nothing outside the tempdir is touched.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

import simple_coding_agent.cli as cli_mod
from simple_coding_agent.cli import main


def test_cli_main_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    rc = main([])
    captured = capsys.readouterr()

    assert rc == 0
    # Header and final-answer sections appear
    assert "MockProvider demo" in captured.out
    assert "Final answer" in captured.out
    # LoopStatus.COMPLETED prints as its value "completed"
    assert "completed" in captured.out.lower()
    # All three scripted tool calls left visible traces
    assert "read_file" in captured.out
    assert "search_text" in captured.out
    assert "write_file" in captured.out
    # Generated REPORT.md was reported as existing inside the workspace
    assert "REPORT.md" in captured.out
    assert "exists=True" in captured.out


def test_cli_repl_flag_dispatches_to_repl_handler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`--repl` must invoke the REPL handler, not the one-shot demo."""
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))

    dispatched = {"value": False}

    def _spy(*_args: object, **_kwargs: object) -> int:
        dispatched["value"] = True
        return 0

    monkeypatch.setattr(cli_mod, "_run_repl", _spy)
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    assert dispatched["value"] is True


def test_cli_max_steps_flag_default_is_10(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Without `--max-steps`, the REPL loop must default to 10."""
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))

    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = list(getattr(cli_mod, "_LAST_LOOPS", []))
    assert loops, "REPL should have built at least one AgentLoop"
    assert loops[0]._max_steps == 10


def test_cli_shell_mode_defaults_to_mock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Patch 4 (Cap1): without `--shell-mode` the run_shell tool stays MOCK."""
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))

    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = list(getattr(cli_mod, "_LAST_LOOPS", []))
    assert loops, "REPL should have built at least one AgentLoop"
    run_shell_tool = loops[-1]._registry.get("run_shell")
    output = run_shell_tool.fn(command="pwd")
    assert "[mock]" in output


def test_cli_shell_mode_flag_threads_to_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Patch 4 (Cap1): `--shell-mode allowlist` makes run_shell execute."""
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))

    rc = main([
        "--repl",
        "--shell-mode", "allowlist",
        "--workspace", str(tmp_path),
    ])
    assert rc == 0
    loops = list(getattr(cli_mod, "_LAST_LOOPS", []))
    assert loops, "REPL should have built at least one AgentLoop"
    run_shell_tool = loops[-1]._registry.get("run_shell")
    output = run_shell_tool.fn(command="pwd")
    # Real subprocess output, not the MOCK stub block.
    assert "[mock]" not in output
    assert "returncode=0" in output
    assert str(tmp_path.resolve()) in output


# ---------------------------------------------------------------------------
# M1: --verbose flag wiring
# ---------------------------------------------------------------------------

def test_cli_verbose_flag_parses_without_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Argparse must accept `--verbose` in REPL mode."""
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))
    rc = main(["--repl", "--verbose", "--workspace", str(tmp_path)])
    assert rc == 0


def test_cli_verbose_flag_threads_to_run_repl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`--verbose` must reach ``_run_repl(verbose=True)``."""
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))

    seen: dict[str, object] = {}

    def _spy(**kwargs: object) -> int:
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(cli_mod, "_run_repl", _spy)
    rc = main(["--repl", "--verbose", "--workspace", str(tmp_path)])
    assert rc == 0
    assert seen.get("verbose") is True


def test_cli_default_no_verbose_keeps_stderr_silent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without ``--verbose``, no ``[trace]`` lines hit stderr."""
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr("sys.stdin", io.StringIO("hello world\n/exit\n"))

    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[trace]" not in captured.err


# ---------------------------------------------------------------------------
# M3: --help snapshot — pin the load-bearing flag phrases
# ---------------------------------------------------------------------------


def _capture_help(capsys: pytest.CaptureFixture[str]) -> str:
    """Run ``main(["--help"])`` and return whitespace-normalized help text.

    argparse exits 0 after printing help and line-wraps descriptions, so we
    collapse whitespace runs to single spaces before matching phrases — that
    pins the wording without coupling to the terminal-width wrap points.
    """
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    return " ".join(capsys.readouterr().out.split())


def test_cli_help_snapshot_pins_flag_phrases(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--verbose / --aggressive-thresholds / --max-context-tokens must stay listed."""
    help_text = _capture_help(capsys)
    assert "--verbose" in help_text
    assert "--aggressive-thresholds" in help_text
    assert "--max-context-tokens" in help_text
    # --verbose still advertises the [trace] line stream.
    assert "[trace]" in help_text
    assert "lines to stderr" in help_text


def test_cli_help_snapshot_pins_preset_precedence_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The M2-added precedence wording must survive any help-text rewording."""
    help_text = _capture_help(capsys)
    assert "preset" in help_text
    # Exact M2 phrase, pinned so future edits cannot silently drop it.
    assert "preset value applies" in help_text
