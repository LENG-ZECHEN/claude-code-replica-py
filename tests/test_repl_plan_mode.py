"""Tests for /plan bidirectional toggle, exit_plan_mode tool, and CLI approval gate.

plan-surface M3 — cli.py + plan_mode_tools.py integration.

Covers:
  - /plan from NORMAL: mode → PLAN, prints "Plan mode entered" line, emits trace source=slash (1)
  - /plan from PLAN (toggle back): mode → NORMAL, prints "Plan mode exited" line,
    emits trace source=slash, transcript history is preserved (1)
  - /help lists /plan with the toggle description (1)
  - Full E2E: model enters plan mode via tool, calls exit_plan_mode, approved → NORMAL (1)
  - Full E2E: model enters plan mode via tool, calls exit_plan_mode, rejected → stays PLAN (1)
  - openai_cli REPL: /plan toggle smoke test via _drive_repl_session (1)
"""
from __future__ import annotations

from pathlib import Path

import pytest

import simple_coding_agent.claude_md as cm
from simple_coding_agent.cli import (
    _REPL_HELP_TEXT,
    _build_repl_loop,
    _drive_repl_session,
    _handle_slash_command,
)
from simple_coding_agent.memory import SessionMemory
from simple_coding_agent.permission import PermissionMode
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.trace import StderrTracer


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


# ---------------------------------------------------------------------------
# /plan bidirectional toggle tests
# ---------------------------------------------------------------------------

def test_slash_plan_normal_to_plan_flips_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """/plan from NORMAL switches to PLAN and prints confirmation."""
    loop = _build_repl_loop(tmp_path)
    assert loop._permission_mode == PermissionMode.NORMAL

    _handle_slash_command("/plan", loop)

    assert loop._permission_mode == PermissionMode.PLAN
    out = capsys.readouterr().out
    assert "Plan mode entered" in out


def test_slash_plan_normal_to_plan_emits_slash_trace(tmp_path: Path) -> None:
    """/plan from NORMAL emits a 'permission' trace with source=slash."""
    trace_lines: list[str] = []

    class _CapTracer(StderrTracer):
        def emit(self, channel: str, /, **fields: object) -> None:
            trace_lines.append(f"[{channel}] " + " ".join(f"{k}={v}" for k, v in fields.items()))

    loop = _build_repl_loop(tmp_path, tracer=_CapTracer())
    _handle_slash_command("/plan", loop)

    assert any(
        "permission" in line and "slash" in line
        for line in trace_lines
    ), f"Expected permission/slash trace, got: {trace_lines}"


def test_slash_plan_plan_to_normal_flips_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """/plan from PLAN switches back to NORMAL and prints confirmation,
    transcript history is preserved."""
    loop = _build_repl_loop(tmp_path, provider=MockProvider([
        MockProvider.direct_answer("hello"),
        MockProvider.direct_answer("world"),
    ]))
    # Drive one turn so transcript has messages
    loop.run("first question")
    msgs_before = list(loop._transcript.all_messages())
    assert len(msgs_before) > 0

    # Enter plan mode first
    _handle_slash_command("/plan", loop)
    assert loop._permission_mode == PermissionMode.PLAN

    # Toggle back
    _handle_slash_command("/plan", loop)

    assert loop._permission_mode == PermissionMode.NORMAL
    out = capsys.readouterr().out
    assert "Plan mode exited" in out

    # Transcript must be preserved across the mode transition
    msgs_after = list(loop._transcript.all_messages())
    assert msgs_after == msgs_before, "Transcript must be preserved across /plan toggle"


def test_slash_plan_toggle_emits_slash_trace_on_exit(tmp_path: Path) -> None:
    """/plan toggle back (PLAN→NORMAL) also emits source=slash trace."""
    trace_lines: list[str] = []

    class _CapTracer(StderrTracer):
        def emit(self, channel: str, /, **fields: object) -> None:
            trace_lines.append(f"[{channel}] " + " ".join(f"{k}={v}" for k, v in fields.items()))

    loop = _build_repl_loop(tmp_path, tracer=_CapTracer())
    # Enter plan mode
    loop._set_permission_mode(PermissionMode.PLAN, source="slash")
    trace_lines.clear()
    # Toggle back
    _handle_slash_command("/plan", loop)

    assert any(
        "permission" in line and "slash" in line
        for line in trace_lines
    ), f"Expected permission/slash trace on exit, got: {trace_lines}"


# ---------------------------------------------------------------------------
# /help lists /plan
# ---------------------------------------------------------------------------

def test_help_lists_plan_command() -> None:
    assert "/plan" in _REPL_HELP_TEXT
    assert "plan mode" in _REPL_HELP_TEXT.lower()


# ---------------------------------------------------------------------------
# Full E2E: model-driven exit via exit_plan_mode tool
# ---------------------------------------------------------------------------

def test_e2e_exit_plan_mode_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Model enters plan mode, calls exit_plan_mode, user approves → NORMAL."""
    monkeypatch.setattr("builtins.input", lambda _: "y")

    provider = MockProvider([
        MockProvider.tool_call("enter_plan_mode", {}),
        MockProvider.tool_call("exit_plan_mode", {"plan": "Do A then B then C"}),
        MockProvider.direct_answer("done"),
    ])
    loop = _build_repl_loop(tmp_path, provider=provider)
    loop.run("please plan and then execute")

    assert loop._permission_mode == PermissionMode.NORMAL


def test_e2e_exit_plan_mode_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Model enters plan mode, calls exit_plan_mode, user rejects → stays PLAN."""
    monkeypatch.setattr("builtins.input", lambda _: "n")

    provider = MockProvider([
        MockProvider.tool_call("enter_plan_mode", {}),
        MockProvider.tool_call("exit_plan_mode", {"plan": "Do A then B"}),
        MockProvider.direct_answer("ok I'll refine"),
    ])
    loop = _build_repl_loop(tmp_path, provider=provider)
    loop.run("please plan")

    assert loop._permission_mode == PermissionMode.PLAN


# ---------------------------------------------------------------------------
# openai_cli REPL smoke test: _drive_repl_session inherits /plan
# ---------------------------------------------------------------------------

def test_drive_repl_session_plan_toggle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/plan toggle works inside _drive_repl_session (openai_cli inherits this)."""
    inputs = ["/plan", "/exit"]
    input_iter = iter(inputs)

    def _fake_input(_prompt: str) -> str:
        try:
            return next(input_iter)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", _fake_input)

    loop = _build_repl_loop(tmp_path)
    session_memory = SessionMemory()
    session_mem_path = tmp_path / "sess.json"

    rc = _drive_repl_session(
        loop,
        stream=False,
        session_memory=session_memory,
        session_mem_path=session_mem_path,
        max_turns=None,
    )

    assert rc == 0
    assert loop._permission_mode == PermissionMode.PLAN
