"""Phase 10: CLI smoke test -- proves the MockProvider demo runs cleanly.

Lightweight by design: no network, no LLM, no API key. The CLI uses
``tempfile.TemporaryDirectory`` so nothing outside the tempdir is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_coding_agent.cli import main


def test_cli_main_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    rc = main()
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
