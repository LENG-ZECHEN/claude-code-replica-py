"""M2 (auto-memory-overhaul): write_memory_entry tool tests.

Written before implementation (TDD — RED phase).

Coverage:
  1. test_write_memory_entry_valid           — happy path, file on disk
  2. test_write_memory_entry_invalid_type    — is_error=True
  3. test_write_memory_entry_invalid_id      — is_error=True
  4. test_write_memory_entry_description_too_long — is_error=True
  5. test_write_memory_entry_secret_in_body  — is_error=True
  6. test_write_memory_entry_upsert          — same id, second body wins
  7. test_tool_not_registered_without_project_memory — absent from registry
  8. test_write_memory_entry_quota_exhausted — 4th call blocked
  9. test_write_memory_entry_quota_resets_per_turn — resets on next run()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from simple_coding_agent.coding_tools import write_memory_entry
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopStatus
from simple_coding_agent.memory import ProjectMemory
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tools import ToolExecutor, ToolRegistry, UnknownToolError
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop_with_memory(
    provider: MockProvider,
    project_memory: ProjectMemory | None,
) -> tuple[AgentLoop, ToolRegistry]:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    transcript = Transcript()
    context_builder = ContextBuilder(budget=budget)
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=context_builder,
        budget=budget,
        registry=registry,
        project_memory=project_memory,
    )
    return loop, registry


def _wme_inputs(id_suffix: str) -> dict[str, Any]:
    """Build valid write_memory_entry tool inputs."""
    return {
        "type": "user",
        "id": f"mem-{id_suffix}",
        "name": "Test Name",
        "description": "A test memory entry",
        "body": "Test body content",
    }


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_write_memory_entry_valid(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    result = write_memory_entry(
        pm, "user", "test-id", "Test Name", "A short description", "body content"
    )
    assert "test-id" in result
    assert (tmp_path / "test-id.md").exists()


# ---------------------------------------------------------------------------
# 2-5. Validation failures (all raise ValueError, surfaced as is_error=True)
# ---------------------------------------------------------------------------


def test_write_memory_entry_invalid_type(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    with pytest.raises(ValueError, match="Invalid type"):
        write_memory_entry(pm, "bad_type", "test-id", "Name", "desc", "body")


def test_write_memory_entry_invalid_id(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    with pytest.raises(ValueError, match="Invalid id"):
        write_memory_entry(pm, "user", "bad..id", "Name", "desc", "body")


def test_write_memory_entry_description_too_long(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    long_desc = "x" * 151
    with pytest.raises(ValueError, match="Description too long"):
        write_memory_entry(pm, "user", "test-id", "Name", long_desc, "body")


def test_write_memory_entry_secret_in_body(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    secret_body = "API_KEY=super-secret-value-1234"
    with pytest.raises(ValueError, match="secret"):
        write_memory_entry(pm, "user", "test-id", "Name", "desc", secret_body)


# ---------------------------------------------------------------------------
# 6. Upsert semantics
# ---------------------------------------------------------------------------


def test_write_memory_entry_upsert(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    write_memory_entry(pm, "user", "shared-id", "First Name", "desc", "first body")
    write_memory_entry(pm, "feedback", "shared-id", "Second Name", "desc", "second body")
    entry = pm.load("shared-id")
    assert entry is not None
    assert "second body" in entry.body
    assert entry.name == "Second Name"


# ---------------------------------------------------------------------------
# 7. Tool registration gating
# ---------------------------------------------------------------------------


def test_tool_not_registered_without_project_memory(tmp_path: Path) -> None:
    provider = MockProvider([MockProvider.direct_answer("ok")])
    _, registry = _make_loop_with_memory(provider, None)
    with pytest.raises(UnknownToolError):
        registry.get("write_memory_entry")


def test_tool_registered_with_project_memory(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    provider = MockProvider([MockProvider.direct_answer("ok")])
    _, registry = _make_loop_with_memory(provider, pm)
    tool = registry.get("write_memory_entry")
    assert tool.name == "write_memory_entry"


# ---------------------------------------------------------------------------
# 8. Quota: 4th write in same run() is blocked
# ---------------------------------------------------------------------------


def test_write_memory_entry_quota_exhausted(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    provider = MockProvider([
        MockProvider.tool_call("write_memory_entry", _wme_inputs("1")),
        MockProvider.tool_call("write_memory_entry", _wme_inputs("2")),
        MockProvider.tool_call("write_memory_entry", _wme_inputs("3")),
        MockProvider.tool_call("write_memory_entry", _wme_inputs("4")),
        MockProvider.direct_answer("done"),
    ])
    loop, _ = _make_loop_with_memory(provider, pm)
    result = loop.run("save memories")

    assert result.status == LoopStatus.COMPLETED
    # 4 tool steps + 1 final-answer step
    assert len(result.steps) == 5
    # First 3 writes succeed
    for i in range(3):
        assert not result.steps[i].tool_results[0].is_error, f"step {i} should not be error"
    # 4th write is quota error
    assert result.steps[3].tool_results[0].is_error is True
    assert "quota exhausted" in result.steps[3].tool_results[0].content


# ---------------------------------------------------------------------------
# 9. Quota resets at the start of the next run()
# ---------------------------------------------------------------------------


def test_write_memory_entry_quota_resets_per_turn(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    # Single provider dequeues across both run() calls
    provider = MockProvider([
        # Turn 1: 3 writes (all should succeed)
        MockProvider.tool_call("write_memory_entry", _wme_inputs("a1")),
        MockProvider.tool_call("write_memory_entry", _wme_inputs("a2")),
        MockProvider.tool_call("write_memory_entry", _wme_inputs("a3")),
        MockProvider.direct_answer("done turn 1"),
        # Turn 2: 1 write (should succeed because quota is reset)
        MockProvider.tool_call("write_memory_entry", _wme_inputs("b1")),
        MockProvider.direct_answer("done turn 2"),
    ])
    loop, _ = _make_loop_with_memory(provider, pm)

    result1 = loop.run("turn 1")
    assert result1.status == LoopStatus.COMPLETED
    # All 3 writes in turn 1 succeed
    for i in range(3):
        assert not result1.steps[i].tool_results[0].is_error, f"turn 1 step {i} should not be error"

    result2 = loop.run("turn 2")
    assert result2.status == LoopStatus.COMPLETED
    # Write in turn 2 succeeds (quota was reset to 0)
    assert not result2.steps[0].tool_results[0].is_error
