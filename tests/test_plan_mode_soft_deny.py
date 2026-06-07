"""Tests for plan-mode soft-deny in AgentLoop._execute_one.

plan-surface M2 — ToolExecutor soft-deny pre-check.

Covers:
  - write_file ToolCall in plan mode → is_error=True, content has "Plan mode active" (1)
  - run_shell ToolCall in plan mode → same (1)
  - write_memory_entry ToolCall in plan mode → same (1)
  - read_file ToolCall in plan mode → executes normally, is_error=False (1)
  - todo_write ToolCall in plan mode → executes normally (1)
  - plan_mode_write_attempts metric bumps once per soft-deny (1)
"""
from __future__ import annotations

from pathlib import Path

import pytest

import simple_coding_agent.claude_md as cm
from simple_coding_agent.cli import _build_repl_loop
from simple_coding_agent.models import ToolCall, ToolResult
from simple_coding_agent.permission import PermissionMode
from simple_coding_agent.provider import MockProvider


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


def _force_plan_mode(tmp_path: Path) -> tuple[object, MockProvider]:
    """Build a loop and drive it into PLAN mode via the enter_plan_mode tool."""
    # Turn 1: model calls enter_plan_mode; turn 2+: model makes write attempts then answers
    responses = [
        MockProvider.tool_call("enter_plan_mode", {}),
        # These get consumed per-run() call in subsequent tests
        *[MockProvider.direct_answer("ok") for _ in range(20)],
    ]
    provider = MockProvider(responses)
    loop = _build_repl_loop(tmp_path, provider=provider)
    loop.run("start planning")
    assert loop._permission_mode == PermissionMode.PLAN, "setup failed: loop not in PLAN mode"
    return loop, provider


def _execute_one_directly(loop: object, name: str, inputs: dict) -> ToolResult:
    """Call loop._execute_one() with a synthetic ToolCall."""
    call = ToolCall(id="test-id", name=name, input=inputs)
    return loop._execute_one(call)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Soft-deny tests (write tools blocked)
# ---------------------------------------------------------------------------

def test_write_file_soft_denied_in_plan_mode(tmp_path: Path) -> None:
    loop, _ = _force_plan_mode(tmp_path)
    result = _execute_one_directly(loop, "write_file", {"path": "x.txt", "content": "hi"})
    assert result.is_error is True
    assert "Plan mode active" in result.content
    assert "'write_file' is not allowed" in result.content


def test_run_shell_soft_denied_in_plan_mode(tmp_path: Path) -> None:
    loop, _ = _force_plan_mode(tmp_path)
    result = _execute_one_directly(loop, "run_shell", {"command": "pwd"})
    assert result.is_error is True
    assert "Plan mode active" in result.content
    assert "'run_shell' is not allowed" in result.content


def test_write_memory_entry_soft_denied_in_plan_mode(tmp_path: Path) -> None:
    loop, _ = _force_plan_mode(tmp_path)
    result = _execute_one_directly(
        loop, "write_memory_entry",
        {"type": "user", "id": "test", "name": "n", "description": "d", "body": "b"},
    )
    assert result.is_error is True
    assert "Plan mode active" in result.content
    assert "'write_memory_entry' is not allowed" in result.content


# ---------------------------------------------------------------------------
# Allowed tools (read-only) still work in plan mode
# ---------------------------------------------------------------------------

def test_read_file_allowed_in_plan_mode(tmp_path: Path) -> None:
    # Write a real file so read_file has something to return
    (tmp_path / "hello.txt").write_text("world")
    loop, _ = _force_plan_mode(tmp_path)
    result = _execute_one_directly(loop, "read_file", {"path": "hello.txt"})
    assert result.is_error is False
    assert "world" in result.content


def test_todo_write_allowed_in_plan_mode(tmp_path: Path) -> None:
    """todo_write is read_only=True, so it should execute in plan mode."""
    loop, _ = _force_plan_mode(tmp_path)
    todos_payload = [
        {"content": "do thing", "status": "pending", "activeForm": "doing thing"},
    ]
    result = _execute_one_directly(loop, "todo_write", {"todos": todos_payload})
    assert result.is_error is False


# ---------------------------------------------------------------------------
# Metric tracking
# ---------------------------------------------------------------------------

def test_plan_mode_write_attempts_metric_bumps_on_soft_deny(tmp_path: Path) -> None:
    loop, _ = _force_plan_mode(tmp_path)
    before = loop._metrics.plan_mode_write_attempts
    _execute_one_directly(loop, "write_file", {"path": "a.txt", "content": "x"})
    assert loop._metrics.plan_mode_write_attempts == before + 1
    _execute_one_directly(loop, "run_shell", {"command": "pwd"})
    assert loop._metrics.plan_mode_write_attempts == before + 2
