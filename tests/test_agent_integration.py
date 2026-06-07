"""Phase 9: AgentLoop + safe coding-tools end-to-end integration tests.

TDD red-then-green. These tests script the LLM via MockProvider, register the
real coding-tool wrappers via build_default_registry, and drive the existing
AgentLoop. They cover factory shape, single-tool flows, a multi-step
read -> search -> write flow, workspace and secret protection, unknown-tool
handling, and transcript inspection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopStatus
from simple_coding_agent.models import MessageType, Role
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tool_registry_factory import build_default_registry
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Fixtures + helper
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A small workspace with one source file, one readme, and one secret."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "main.py").write_text(
        "def main():\n    print('hello world')\n",
        encoding="utf-8",
    )
    (ws / "README.md").write_text("# Project\n", encoding="utf-8")
    (ws / ".env").write_text("SECRET=do_not_read\n", encoding="utf-8")
    return ws


def _make_loop(
    provider: MockProvider,
    registry: ToolRegistry,
    transcript: Transcript | None = None,
) -> tuple[AgentLoop, Transcript]:
    """Wire a minimal AgentLoop around the registry produced by the factory."""
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    t = transcript or Transcript()
    builder = ContextBuilder(budget=budget)
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=t,
        context_builder=builder,
        budget=budget,
        registry=registry,
    )
    return loop, t


# ---------------------------------------------------------------------------
# Factory shape
# ---------------------------------------------------------------------------


def test_factory_returns_tool_registry(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    assert isinstance(registry, ToolRegistry)


def test_factory_registers_all_five_tools(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    names = {t.name for t in registry.all_tools()}
    # M4 added snip_history; plan-surface M2 added enter_plan_mode.
    assert names == {
        "list_files",
        "read_file",
        "write_file",
        "search_text",
        "run_shell",
        "snip_history",
        "enter_plan_mode",
    }


def test_factory_tools_have_schemas(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    api_spec = registry.to_api_format()
    assert len(api_spec) == 7  # five coding tools + snip_history (M4) + enter_plan_mode (M2)
    for entry in api_spec:
        assert entry["name"]
        assert entry["description"]
        assert entry["input_schema"]["type"] == "object"


# ---------------------------------------------------------------------------
# Single-tool scripted flows
# ---------------------------------------------------------------------------


def test_agent_loop_executes_read_file(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call("read_file", {"path": "src/main.py"}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, _ = _make_loop(provider, registry)

    result = loop.run("read src/main.py")

    assert result.status == LoopStatus.COMPLETED
    assert result.answer == "done"
    tr = result.steps[0].tool_results[0]
    assert not tr.is_error
    assert "def main" in tr.content


def test_agent_loop_executes_search_text(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call("search_text", {"pattern": "hello"}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, _ = _make_loop(provider, registry)

    result = loop.run("search for hello")

    assert result.status == LoopStatus.COMPLETED
    tr = result.steps[0].tool_results[0]
    assert not tr.is_error
    assert "src/main.py" in tr.content


def test_agent_loop_executes_write_file(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call(
            "write_file",
            {"path": "out.txt", "content": "hello from agent"},
            id="tu_1",
        ),
        MockProvider.direct_answer("done"),
    ])
    loop, _ = _make_loop(provider, registry)

    result = loop.run("write out.txt")

    assert result.status == LoopStatus.COMPLETED
    assert not result.steps[0].tool_results[0].is_error
    assert (workspace / "out.txt").read_text(encoding="utf-8") == "hello from agent"


# ---------------------------------------------------------------------------
# Multi-step flow: read -> search -> write -> answer
# ---------------------------------------------------------------------------


def test_read_search_write_end_to_end(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call("read_file", {"path": "src/main.py"}, id="tu_r"),
        MockProvider.tool_call("search_text", {"pattern": "hello"}, id="tu_s"),
        MockProvider.tool_call(
            "write_file",
            {"path": "report.md", "content": "found hello in src/main.py\n"},
            id="tu_w",
        ),
        MockProvider.direct_answer("wrote report.md"),
    ])
    loop, _ = _make_loop(provider, registry)

    result = loop.run("read main, search hello, write report")

    assert result.status == LoopStatus.COMPLETED
    assert result.answer == "wrote report.md"
    assert len(result.steps) == 4  # three tool turns + final text turn

    report = workspace / "report.md"
    assert report.exists()
    assert report.read_text(encoding="utf-8") == "found hello in src/main.py\n"

    # No tool errors along the way
    for step in result.steps[:3]:
        for tr in step.tool_results:
            assert not tr.is_error


# ---------------------------------------------------------------------------
# Workspace boundary and secret protection are preserved through the registry
# ---------------------------------------------------------------------------


def test_workspace_boundary_preserved_through_registry(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call("read_file", {"path": "../escape.txt"}, id="tu_1"),
        MockProvider.direct_answer("rejected as expected"),
    ])
    loop, _ = _make_loop(provider, registry)

    result = loop.run("try to escape the workspace")

    assert result.status == LoopStatus.COMPLETED
    tr = result.steps[0].tool_results[0]
    assert tr.is_error
    # WorkspaceBoundaryError message uses "escape" / "workspace"
    assert "escape" in tr.content.lower() or "workspace" in tr.content.lower()


def test_secret_protection_preserved_through_registry(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call("read_file", {"path": ".env"}, id="tu_1"),
        MockProvider.direct_answer("rejected as expected"),
    ])
    loop, _ = _make_loop(provider, registry)

    result = loop.run("try to read the .env")

    assert result.status == LoopStatus.COMPLETED
    tr = result.steps[0].tool_results[0]
    assert tr.is_error
    assert "secret" in tr.content.lower() or ".env" in tr.content
    # The real secret content must not leak into the tool result
    assert "do_not_read" not in tr.content


# ---------------------------------------------------------------------------
# Unknown tool still becomes an error ToolResult (loop does not crash)
# ---------------------------------------------------------------------------


def test_unknown_tool_becomes_error_result(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call("totally_made_up_tool", {}, id="tu_1"),
        MockProvider.direct_answer("recovered"),
    ])
    loop, _ = _make_loop(provider, registry)

    result = loop.run("call ghost tool")

    assert result.status == LoopStatus.COMPLETED
    tr = result.steps[0].tool_results[0]
    assert tr.is_error
    assert "unknown" in tr.content.lower()
    assert "totally_made_up_tool" in tr.content


# ---------------------------------------------------------------------------
# Transcript contains full turn structure
# ---------------------------------------------------------------------------


def test_transcript_contains_user_tooluse_toolresult_answer(
    workspace: Path,
) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call("read_file", {"path": "README.md"}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, transcript = _make_loop(provider, registry)
    loop.run("read README")

    msgs = transcript.all_messages()
    # user input -> assistant tool_use -> user tool_result -> assistant text
    assert len(msgs) == 4
    assert msgs[0].role == Role.USER
    assert msgs[0].type == MessageType.TEXT
    assert msgs[1].role == Role.ASSISTANT
    assert msgs[1].type == MessageType.TOOL_USE
    assert msgs[2].role == Role.USER
    assert msgs[2].type == MessageType.TOOL_RESULT
    assert msgs[2].is_meta
    assert msgs[3].role == Role.ASSISTANT
    assert msgs[3].type == MessageType.TEXT
    assert msgs[3].content == "done"


# ---------------------------------------------------------------------------
# run_shell is wired in MOCK mode (no real process execution)
# ---------------------------------------------------------------------------


def test_run_shell_tool_uses_mock_mode(workspace: Path) -> None:
    registry = build_default_registry(workspace)
    provider = MockProvider([
        MockProvider.tool_call("run_shell", {"command": "pwd"}, id="tu_1"),
        MockProvider.direct_answer("done"),
    ])
    loop, _ = _make_loop(provider, registry)

    result = loop.run("run pwd")

    assert result.status == LoopStatus.COMPLETED
    tr = result.steps[0].tool_results[0]
    assert not tr.is_error
    assert "mock" in tr.content.lower()
