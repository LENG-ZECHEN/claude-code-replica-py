"""Tests for TodoWrite V1 REPL integration.

Covers: /todos slash command, 10-turn cycle, CLI flags --todo-reminder-turns /
--no-todo-reminder, and quiescence when todo_write is not registered.

All cases use MockProvider / deterministic inputs; no network, no API key.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

import simple_coding_agent.claude_md as cm
import simple_coding_agent.cli as cli_mod
from simple_coding_agent.cli import _build_repl_loop, _handle_slash_command, main
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.provider import MockProvider, ProviderResponse
from simple_coding_agent.tool_registry_factory import build_default_registry
from simple_coding_agent.tools import ToolExecutor
from simple_coding_agent.trace import NullTracer, StderrTracer
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_user_claude_md(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


def _direct_answers(n: int) -> list[ProviderResponse]:
    return [MockProvider.direct_answer("ok") for _ in range(n)]


def _build_loop_with_todo(
    tmp_path: Path,
    *,
    todo_nudge_enabled: bool = True,
    todo_reminder_turns: int = 10,
    tracer: Any = None,
) -> tuple[AgentLoop, MockProvider]:
    """Build an AgentLoop with todo_write registered and a long mock script."""
    provider = MockProvider(_direct_answers(200))
    loop = _build_repl_loop(
        tmp_path,
        provider=provider,
        todo_nudge_enabled=todo_nudge_enabled,
        todo_reminder_turns=todo_reminder_turns,
        tracer=tracer or NullTracer(),
    )
    return loop, provider


def _messages_at_turn(provider: MockProvider, turn: int) -> list[dict[str, Any]]:
    """Return the messages list that was passed to the provider at 1-based turn."""
    return list(provider.call_history[turn - 1].messages)


def _has_todo_nudge_content(messages: list[dict[str, Any]]) -> bool:
    """True if any message in messages contains the TODO reminder text."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and "hasn't been used recently" in content:
            return True
        if isinstance(content, list):
            for block in content:
                text = block.get("text", "") if isinstance(block, dict) else ""
                if "hasn't been used recently" in text:
                    return True
    return False


# ---------------------------------------------------------------------------
# /todos slash command
# ---------------------------------------------------------------------------

def test_todos_shows_empty_on_fresh_loop(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    loop, _ = _build_loop_with_todo(tmp_path)
    _handle_slash_command("/todos", loop)
    out = capsys.readouterr().out
    assert "no todos" in out.lower() or out.strip() == "(no todos)" or "(no todos)" in out


def test_todos_shows_glyphs_after_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Build a provider that scripted a todo_write call on turn 1
    todo_payload = {
        "todos": [
            {"content": "Fix bug", "status": "pending", "activeForm": "Fixing bug"},
            {"content": "Add tests", "status": "in_progress", "activeForm": "Adding tests"},
            {"content": "Deploy", "status": "completed", "activeForm": "Deploying"},
        ]
    }
    provider = MockProvider([
        MockProvider.tool_call("todo_write", todo_payload, id="tu_td"),
        *_direct_answers(10),
    ])
    loop = _build_repl_loop(tmp_path, provider=provider)
    loop.run("do tasks")

    capsys.readouterr()  # clear
    _handle_slash_command("/todos", loop)
    out = capsys.readouterr().out
    # Should show glyphs for each status
    assert "☐" in out or "pending" in out.lower()
    assert "▶" in out or "in_progress" in out.lower()
    assert "☑" in out or "completed" in out.lower()


# ---------------------------------------------------------------------------
# CORE 10-turn cycle test
# ---------------------------------------------------------------------------

def test_todo_nudge_cycle(tmp_path: Path) -> None:
    """Turn 10: inject. Turns 11-19: cooldown (no injection). Turn 20: re-inject."""
    loop, provider = _build_loop_with_todo(tmp_path, todo_reminder_turns=10)

    # Run 20 turns, no tool calls → todo_write is NEVER called
    for i in range(20):
        loop.run(f"turn {i + 1}")

    # Turn 10: must contain reminder
    assert _has_todo_nudge_content(_messages_at_turn(provider, 10)), \
        "Expected ATTACHMENT_TODO_NUDGE at turn 10"

    # Turns 11-19: must NOT contain reminder (cooldown)
    for t in range(11, 20):
        assert not _has_todo_nudge_content(_messages_at_turn(provider, t)), \
            f"Expected NO ATTACHMENT_TODO_NUDGE at turn {t} (cooldown)"

    # Turn 20: must re-inject
    assert _has_todo_nudge_content(_messages_at_turn(provider, 20)), \
        "Expected ATTACHMENT_TODO_NUDGE at turn 20 (cycle resumes)"


# ---------------------------------------------------------------------------
# --todo-reminder-turns 3
# ---------------------------------------------------------------------------

def test_todo_reminder_turns_3(tmp_path: Path) -> None:
    """With n=3: inject at turn 3, cooldown 4-5, re-inject at turn 6."""
    loop, provider = _build_loop_with_todo(tmp_path, todo_reminder_turns=3)

    for i in range(10):
        loop.run(f"turn {i + 1}")

    # Turn 3: inject
    assert _has_todo_nudge_content(_messages_at_turn(provider, 3)), \
        "Expected nudge at turn 3 (n=3)"
    # Turns 4-5: cooldown
    for t in (4, 5):
        assert not _has_todo_nudge_content(_messages_at_turn(provider, t)), \
            f"Expected NO nudge at turn {t} (cooldown with n=3)"
    # Turn 6: re-inject
    assert _has_todo_nudge_content(_messages_at_turn(provider, 6)), \
        "Expected nudge at turn 6 (cycle resumes with n=3)"


# ---------------------------------------------------------------------------
# --no-todo-reminder
# ---------------------------------------------------------------------------

def test_no_todo_reminder_flag(tmp_path: Path) -> None:
    """With todo_nudge_enabled=False: no injection even after 30 turns."""
    loop, provider = _build_loop_with_todo(tmp_path, todo_nudge_enabled=False)

    for i in range(30):
        loop.run(f"turn {i + 1}")

    for t in range(1, 31):
        assert not _has_todo_nudge_content(_messages_at_turn(provider, t)), \
            f"Expected NO nudge at turn {t} with --no-todo-reminder"


# ---------------------------------------------------------------------------
# Quiescence when todo_write is not registered
# ---------------------------------------------------------------------------

def test_quiescent_without_todo_write(tmp_path: Path) -> None:
    """When todo_write is NOT in the registry, the nudge machinery is silent."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    provider = MockProvider(_direct_answers(35))
    transcript = Transcript()
    registry = build_default_registry(tmp_path, transcript=transcript)
    # Deliberately do NOT register todo_write
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    builder = ContextBuilder(budget=budget, tracer=tracer)
    metrics = MetricsCollector()
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        metrics=metrics,
        tracer=tracer,
        todo_nudge_enabled=True,  # enabled but tool not registered → quiescent
    )

    for i in range(30):
        loop.run(f"turn {i + 1}")

    trace_output = buf.getvalue()
    assert "[trace] [todo]" not in trace_output, \
        "todo channel must not emit when todo_write is not registered"
    assert metrics.todo_nudges_armed == 0, \
        "todo_nudges_armed must stay 0 when todo_write not registered"

    # No ATTACHMENT_TODO_NUDGE in any provider call
    for t in range(1, 31):
        assert not _has_todo_nudge_content(_messages_at_turn(provider, t)), \
            f"No nudge message should appear at turn {t}"


# ---------------------------------------------------------------------------
# CLI integration: --no-todo-reminder flag via argparse
# ---------------------------------------------------------------------------

def test_cli_no_todo_reminder_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))
    rc = main(["--repl", "--no-todo-reminder", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = list(getattr(cli_mod, "_LAST_LOOPS", []))
    assert loops, "Expected at least one loop"
    loop = loops[-1]
    assert not loop._todo_nudge_machinery_enabled, \
        "_todo_nudge_machinery_enabled must be False with --no-todo-reminder"


def test_cli_todo_reminder_turns_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))
    rc = main(["--repl", "--todo-reminder-turns", "3", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = list(getattr(cli_mod, "_LAST_LOOPS", []))
    assert loops
    loop = loops[-1]
    assert loop._todo_reminder_turns == 3


def test_todo_nudge_fires_only_on_first_inner_turn(tmp_path: Path) -> None:
    """Follow-up fix (Item 2 from post-archive review-time deferred ledger):
    `_todo_nudge` was captured once per loop.run() but reused on every inner
    agent turn within that user input, causing the same nudge to be prepended
    to every `build()` call. Mirrors TS getTodoReminderTurnCounts which fires
    per user turn, not per inner agent turn. The fix clears `_todo_nudge` to
    None after the first successful inner-turn build()."""
    from simple_coding_agent.coding_tools import ShellMode
    from simple_coding_agent.context import ContextBudget, ContextBuilder
    from simple_coding_agent.models import ToolCall
    from simple_coding_agent.provider import TokenUsage
    from simple_coding_agent.todo import TodoItem, TodoStatus
    from simple_coding_agent.todo_tool import register_todo_write_tool

    (tmp_path / "f1.txt").write_text("a\n")
    (tmp_path / "f2.txt").write_text("b\n")
    (tmp_path / "f3.txt").write_text("c\n")

    transcript = Transcript()
    registry = build_default_registry(tmp_path, shell_mode=ShellMode.MOCK, transcript=transcript)

    _todos_state: list[TodoItem] = []
    register_todo_write_tool(
        registry,
        lambda: list(_todos_state),
        lambda new: (_todos_state.__init__(new) or None),  # type: ignore[misc]
    )

    def _tool_call_resp(call_id: str, path: str) -> ProviderResponse:
        return ProviderResponse(
            text="",
            tool_calls=[ToolCall(id=call_id, name="read_file", input={"path": path})],
            usage=TokenUsage(),
            stop_reason="tool_use",
        )

    provider = MockProvider([
        _tool_call_resp("c1", "f1.txt"),
        _tool_call_resp("c2", "f2.txt"),
        _tool_call_resp("c3", "f3.txt"),
        MockProvider.direct_answer("done"),
    ])

    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    builder = ContextBuilder(budget=budget)

    # Capture todo_nudge kwarg seen by each build() call.
    nudge_kwarg_history: list[bool] = []
    real_build = builder.build

    def traced_build(**kwargs):  # type: ignore[no-untyped-def]
        nudge_kwarg_history.append(kwargs.get("todo_nudge") is not None)
        return real_build(**kwargs)

    builder.build = traced_build  # type: ignore[assignment]

    loop = AgentLoop(
        provider=provider,
        tool_executor=ToolExecutor(registry),
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        todo_nudge_enabled=True,
        todo_reminder_turns=2,
    )
    # Pre-arm the nudge so the first inner turn definitely receives it.
    loop._turns_since_last_todo_write = 10
    loop._turns_since_last_todo_reminder = 10
    loop._todos = [TodoItem(content="x", status=TodoStatus.IN_PROGRESS, activeForm="x-ing")]

    result = loop.run("inspect 3 files")
    assert result.status.name == "COMPLETED"
    # 4 inner turns observed (3 tool turns + 1 final). Only the FIRST should
    # carry the todo_nudge; the rest must be None.
    assert nudge_kwarg_history == [True, False, False, False]
    # The arm-counter metric must still bump exactly once for this user input.
    assert loop._metrics.todo_nudges_armed == 1
