"""Tests for PlanRejectedError and register_exit_plan_mode_tool.

plan-surface M3 — plan_mode_tools.py + MetricsCollector changes.

Covers:
  - register_exit_plan_mode_tool produces a Tool with read_only=True (1)
  - schema validation: missing plan rejected (1)
  - schema validation: empty plan rejected (1)
  - schema validation: non-string plan rejected (1)
  - approval_callback returns True → mode_setter called with NORMAL, returns approval text (1)
  - approval_callback returns False → PlanRejectedError raised with rejection text (1)
  - End-to-end through ToolExecutor: approve → ToolResult is_error=False (1)
  - End-to-end through ToolExecutor: reject → ToolResult is_error=True, rejection text (1)
"""
from __future__ import annotations

from pathlib import Path

import pytest

import simple_coding_agent.claude_md as cm
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.permission import PermissionMode
from simple_coding_agent.plan_mode_tools import PlanRejectedError, register_exit_plan_mode_tool
from simple_coding_agent.tools import ToolExecutor, ToolRegistry


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


# ---------------------------------------------------------------------------
# Unit tests for PlanRejectedError
# ---------------------------------------------------------------------------

def test_plan_rejected_error_is_runtime_error() -> None:
    err = PlanRejectedError("msg")
    assert isinstance(err, RuntimeError)
    assert str(err) == "msg"


# ---------------------------------------------------------------------------
# Unit tests for register_exit_plan_mode_tool
# ---------------------------------------------------------------------------

def test_register_exit_plan_mode_produces_read_only_tool() -> None:
    registry = ToolRegistry()
    register_exit_plan_mode_tool(
        registry,
        lambda mode: None,
        lambda plan: True,
    )
    tool = registry.get("exit_plan_mode")
    assert tool.read_only is True


def test_exit_plan_mode_schema_rejects_missing_plan() -> None:
    registry = ToolRegistry()
    register_exit_plan_mode_tool(registry, lambda mode: None, lambda plan: True)
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("exit_plan_mode", {})
    assert is_error is True
    low = content.lower()
    assert "plan" in low or "required" in low or "missing" in low


def test_exit_plan_mode_schema_rejects_empty_plan() -> None:
    registry = ToolRegistry()
    register_exit_plan_mode_tool(registry, lambda mode: None, lambda plan: True)
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("exit_plan_mode", {"plan": ""})
    assert is_error is True


def test_exit_plan_mode_schema_rejects_non_string_plan() -> None:
    registry = ToolRegistry()
    register_exit_plan_mode_tool(registry, lambda mode: None, lambda plan: True)
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("exit_plan_mode", {"plan": 123})
    assert is_error is True


def test_exit_plan_mode_approval_calls_mode_setter_and_returns_text() -> None:
    registry = ToolRegistry()
    mode_calls: list[PermissionMode] = []
    register_exit_plan_mode_tool(
        registry,
        lambda mode: mode_calls.append(mode),
        lambda plan: True,  # always approve
    )
    tool = registry.get("exit_plan_mode")
    result = tool.fn(plan="My detailed plan")
    assert mode_calls == [PermissionMode.NORMAL]
    assert result == "Plan approved. Exiting plan mode."


def test_exit_plan_mode_rejection_raises_plan_rejected_error() -> None:
    registry = ToolRegistry()
    mode_calls: list[PermissionMode] = []
    register_exit_plan_mode_tool(
        registry,
        lambda mode: mode_calls.append(mode),
        lambda plan: False,  # always reject
    )
    tool = registry.get("exit_plan_mode")
    with pytest.raises(PlanRejectedError) as exc_info:
        tool.fn(plan="My plan")
    assert "Plan rejected by user" in str(exc_info.value)
    assert mode_calls == []  # mode_setter NOT called on rejection


# ---------------------------------------------------------------------------
# End-to-end through ToolExecutor
# ---------------------------------------------------------------------------

def test_toolexecutor_approve_path_is_not_error() -> None:
    registry = ToolRegistry()
    register_exit_plan_mode_tool(
        registry,
        lambda mode: None,
        lambda plan: True,
    )
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("exit_plan_mode", {"plan": "detailed plan"})
    assert is_error is False
    assert content == "Plan approved. Exiting plan mode."


def test_toolexecutor_reject_path_is_error_with_rejection_text() -> None:
    registry = ToolRegistry()
    register_exit_plan_mode_tool(
        registry,
        lambda mode: None,
        lambda plan: False,
    )
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("exit_plan_mode", {"plan": "detailed plan"})
    assert is_error is True
    assert "Plan rejected by user. Stay in plan mode and refine." in content


# ---------------------------------------------------------------------------
# Metrics wiring (review-fix): the rejection path must bump
# plan_mode_exits_rejected when a MetricsCollector is supplied. Without the
# metrics= kwarg the rejection counter would be permanently zero because the
# rejection branch short-circuits before mode_setter would have bumped it.
# ---------------------------------------------------------------------------

def test_exit_plan_mode_rejection_bumps_metrics_when_supplied() -> None:
    registry = ToolRegistry()
    metrics = MetricsCollector()
    register_exit_plan_mode_tool(
        registry,
        lambda mode: None,
        lambda plan: False,  # always reject
        metrics=metrics,
    )
    tool = registry.get("exit_plan_mode")
    assert metrics.plan_mode_exits_rejected == 0
    with pytest.raises(PlanRejectedError):
        tool.fn(plan="My plan")
    assert metrics.plan_mode_exits_rejected == 1
    assert metrics.plan_mode_exits_approved == 0
    # Second rejection should keep incrementing.
    with pytest.raises(PlanRejectedError):
        tool.fn(plan="Another plan")
    assert metrics.plan_mode_exits_rejected == 2


def test_exit_plan_mode_rejection_without_metrics_does_not_crash() -> None:
    registry = ToolRegistry()
    register_exit_plan_mode_tool(
        registry,
        lambda mode: None,
        lambda plan: False,
        # metrics= omitted — must remain backward-compatible
    )
    tool = registry.get("exit_plan_mode")
    with pytest.raises(PlanRejectedError):
        tool.fn(plan="My plan")


def test_exit_plan_mode_approval_does_not_double_bump_rejected() -> None:
    """Approval path goes through mode_setter (which bumps `_approved` via
    `_set_permission_mode`). The factory must not also bump anything on
    approval, otherwise approval+rejection counts would diverge from total."""
    registry = ToolRegistry()
    metrics = MetricsCollector()
    register_exit_plan_mode_tool(
        registry,
        lambda mode: None,  # no-op mode_setter for this unit test
        lambda plan: True,  # always approve
        metrics=metrics,
    )
    tool = registry.get("exit_plan_mode")
    result = tool.fn(plan="My plan")
    assert result == "Plan approved. Exiting plan mode."
    # The factory must not bump on approval; only mode_setter chain would.
    # Since mode_setter is a no-op here, both counters stay 0.
    assert metrics.plan_mode_exits_approved == 0
    assert metrics.plan_mode_exits_rejected == 0
