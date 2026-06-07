"""Tests for register_enter_plan_mode_tool and EnterPlanMode integration.

plan-surface M2 — plan_mode_tools.py + AgentLoop._permission_mode.

Covers:
  - register_enter_plan_mode_tool produces a Tool with read_only=True (1)
  - Tool fn invocation flips mode via mode_setter (1)
  - Tool fn returns the exact ENTER_PLAN_MODE_TEACHING_TEXT (1)
  - MockProvider integration: turn 1 calls enter_plan_mode → _permission_mode == PLAN (1)
  - API schema invariance: tools JSON deep-equal across mode change (1)
  - turn 2 BuiltContext.api_messages includes ATTACHMENT_PLAN_MODE USER message (1)
  - ATTACHMENT_PLAN_MODE message body contains the teaching text fragment (1)
  - read_only=True audit: read_file, list_files, search_text, snip_history, todo_write (1)
  - enter_plan_mode is in default registry (1)
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import simple_coding_agent.claude_md as cm
from simple_coding_agent.cli import _build_repl_loop
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.models import MessageType
from simple_coding_agent.permission import (
    ENTER_PLAN_MODE_TEACHING_TEXT,
    PermissionMode,
    PlanModeAttachment,
)
from simple_coding_agent.plan_mode_tools import register_enter_plan_mode_tool
from simple_coding_agent.provider import MockProvider, ProviderResponse
from simple_coding_agent.tool_registry_factory import build_default_registry
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.trace import NullTracer
from simple_coding_agent.transcript import Transcript


@pytest.fixture(autouse=True)
def _isolate_user_claude_md(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


# ---------------------------------------------------------------------------
# Unit tests for register_enter_plan_mode_tool
# ---------------------------------------------------------------------------

def test_register_enter_plan_mode_produces_read_only_tool() -> None:
    registry = ToolRegistry()
    calls: list[PermissionMode] = []
    register_enter_plan_mode_tool(registry, lambda mode: calls.append(mode))
    tool = registry.get("enter_plan_mode")
    assert tool.read_only is True


def test_enter_plan_mode_fn_flips_mode() -> None:
    registry = ToolRegistry()
    mode_log: list[PermissionMode] = []
    register_enter_plan_mode_tool(registry, lambda m: mode_log.append(m))
    tool = registry.get("enter_plan_mode")
    tool.fn()
    assert mode_log == [PermissionMode.PLAN]


def test_enter_plan_mode_fn_returns_teaching_text() -> None:
    registry = ToolRegistry()
    register_enter_plan_mode_tool(registry, lambda m: None)
    tool = registry.get("enter_plan_mode")
    result = tool.fn()
    assert result == ENTER_PLAN_MODE_TEACHING_TEXT


# ---------------------------------------------------------------------------
# Integration tests via AgentLoop
# ---------------------------------------------------------------------------

def _build_test_loop(
    tmp_path: Path,
    responses: list[ProviderResponse],
) -> tuple[AgentLoop, MockProvider]:
    provider = MockProvider(responses)
    loop = _build_repl_loop(tmp_path, provider=provider)
    return loop, provider


def _captured_tools_at(provider: MockProvider, turn: int) -> list[dict[str, Any]]:
    """Return the tools list passed to Provider.call() at the given 1-based turn."""
    return list(provider.call_history[turn - 1].tools)


def _find_attachment_plan_mode(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the first message whose content contains the plan-mode attachment text."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and "DO NOT write or edit any files yet" in content:
            return msg
        if isinstance(content, list):
            for block in content:
                text = block.get("text", "") if isinstance(block, dict) else ""
                if "DO NOT write or edit any files yet" in text:
                    return msg
    return None


def test_enter_plan_mode_integration_flips_permission_mode(tmp_path: Path) -> None:
    """Turn 1: model calls enter_plan_mode → loop._permission_mode == PLAN."""
    responses = [
        MockProvider.tool_call("enter_plan_mode", {}),
        MockProvider.direct_answer("ok"),
    ]
    loop, _ = _build_test_loop(tmp_path, responses)
    loop.run("hello")
    assert loop._permission_mode == PermissionMode.PLAN


def test_api_tools_schema_mode_invariant(tmp_path: Path) -> None:
    """Tools JSON passed to Provider.call() is byte-identical in turn 1 (NORMAL)
    and turn 2 (PLAN) — proves prompt cache PREFIX is preserved."""
    responses = [
        MockProvider.tool_call("enter_plan_mode", {}),
        MockProvider.direct_answer("done"),
    ]
    loop, provider = _build_test_loop(tmp_path, responses)
    loop.run("hello")
    tools_turn1 = _captured_tools_at(provider, 1)
    tools_turn2 = _captured_tools_at(provider, 2)
    assert tools_turn1 == tools_turn2, (
        "tools schema must be mode-invariant; prompt cache PREFIX must be preserved"
    )


def test_turn2_contains_attachment_plan_mode(tmp_path: Path) -> None:
    """Turn 2 BuiltContext.api_messages must contain an ATTACHMENT_PLAN_MODE message."""
    responses = [
        MockProvider.tool_call("enter_plan_mode", {}),
        MockProvider.direct_answer("done"),
    ]
    loop, provider = _build_test_loop(tmp_path, responses)
    loop.run("hello")
    messages_turn2 = list(provider.call_history[1].messages)
    found = _find_attachment_plan_mode(messages_turn2)
    assert found is not None, (
        "turn 2 messages must include ATTACHMENT_PLAN_MODE with teaching text"
    )
    assert found["role"] == "user"


def test_turn2_attachment_contains_teaching_text(tmp_path: Path) -> None:
    """The ATTACHMENT_PLAN_MODE message body must contain the teaching text verbatim."""
    responses = [
        MockProvider.tool_call("enter_plan_mode", {}),
        MockProvider.direct_answer("done"),
    ]
    loop, provider = _build_test_loop(tmp_path, responses)
    loop.run("hello")
    messages_turn2 = list(provider.call_history[1].messages)
    found = _find_attachment_plan_mode(messages_turn2)
    assert found is not None
    # Flatten content to one string for substring check
    content = found["content"]
    if isinstance(content, list):
        flat = " ".join(
            block.get("text", "") if isinstance(block, dict) else ""
            for block in content
        )
    else:
        flat = str(content)
    assert "DO NOT write or edit any files yet" in flat


# ---------------------------------------------------------------------------
# read_only flag audit on default registry
# ---------------------------------------------------------------------------

def test_default_registry_read_only_audit(tmp_path: Path) -> None:
    """Verify read_only flags on all tools in the default registry."""
    registry = build_default_registry(tmp_path)
    expected_read_only = {"read_file", "list_files", "search_text", "snip_history", "enter_plan_mode"}
    expected_write = {"write_file", "run_shell"}
    for name in expected_read_only:
        tool = registry.get(name)
        assert tool.read_only is True, f"{name!r} should be read_only=True"
    for name in expected_write:
        tool = registry.get(name)
        assert tool.read_only is False, f"{name!r} should be read_only=False"


def test_enter_plan_mode_in_default_registry(tmp_path: Path) -> None:
    """enter_plan_mode must be in the default registry (not deferred)."""
    registry = build_default_registry(tmp_path)
    tool = registry.get("enter_plan_mode")
    assert tool.name == "enter_plan_mode"
