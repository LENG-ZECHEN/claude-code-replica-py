"""Tests for ForkedAgentRunner (forked_agent.py) — M1 exit gate.

Exit gate assertions (map directly to test cases):
  (a) context_messages ARE injected into the sub-agent's first provider call
      (MockProvider.history[0].messages contains them).
  (b) a tool the gate denies returns is_error=True with the gate's reason
      and NEVER reaches the ToolExecutor/registry.
  (c) max_turns is constructor-configurable; the for/else "max turns reached"
      error is preserved.
  (d) writes still confined to a fresh local store (tested via the
      ExtractMemoriesRunner thin wrapper that delegates to ForkedAgentRunner).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from simple_coding_agent.forked_agent import ForkedAgentRunner
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tools import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _allow_all(name: str, inp: dict[str, Any]) -> tuple[bool, str]:
    return True, ""


def _deny_all(name: str, inp: dict[str, Any]) -> tuple[bool, str]:
    return False, f"Tool '{name}' is not permitted"


def _end_turn(text: str = "done") -> Any:
    return MockProvider.direct_answer(text)


def _make_registry(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    for n in names:
        captured = n
        registry.register(Tool(
            name=captured,
            description=f"Tool {captured}",
            input_schema={"type": "object", "properties": {}},
            fn=lambda captured=captured, **kwargs: f"result:{captured}",
        ))
    return registry


# ---------------------------------------------------------------------------
# (a) Context injection — MockProvider.history[0].messages must contain them
# ---------------------------------------------------------------------------


def test_context_messages_prepended_to_first_call() -> None:
    """(a) context_messages appear at the start of the first provider call."""
    context = [
        {"role": "user", "content": "prior user turn"},
        {"role": "assistant", "content": "prior assistant reply"},
    ]
    provider = MockProvider([_end_turn()])
    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=_allow_all,
        tool_registry=ToolRegistry(),
        max_turns=5,
    )
    runner.run(task_prompt="do the task", context_messages=context)

    first_msgs = provider.history[0].messages
    # context_messages prepended
    assert first_msgs[:2] == context
    # task_prompt follows immediately
    assert first_msgs[2]["content"] == "do the task"
    assert first_msgs[2]["role"] == "user"


def test_empty_context_messages_leaves_single_task_message() -> None:
    """No extra messages when context_messages is empty (default)."""
    provider = MockProvider([_end_turn()])
    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=_allow_all,
        tool_registry=ToolRegistry(),
        max_turns=5,
    )
    runner.run(task_prompt="sole task")

    first_msgs = provider.history[0].messages
    assert len(first_msgs) == 1
    assert first_msgs[0]["content"] == "sole task"


def test_context_messages_snapshot_not_mutated_after_run() -> None:
    """Caller mutating context_messages after run() does not affect messages sent."""
    context: list[dict[str, Any]] = [{"role": "user", "content": "original"}]
    provider = MockProvider([_end_turn()])
    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=_allow_all,
        tool_registry=ToolRegistry(),
        max_turns=5,
    )
    runner.run(task_prompt="task", context_messages=context)
    # Mutate after run — should not affect what was already sent
    context.append({"role": "user", "content": "late injected"})

    first_msgs = provider.history[0].messages
    # Only the original + task_prompt were sent
    assert len(first_msgs) == 2
    assert first_msgs[0]["content"] == "original"


# ---------------------------------------------------------------------------
# (b) Gate deny — is_error=True, reason carried, executor never reached
# ---------------------------------------------------------------------------


def test_gate_deny_returns_error_with_gate_reason() -> None:
    """(b) Gate deny → tool_result with is_error=True carrying gate's reason."""
    deny_reason = "write tools are not allowed in this context"

    def deny_writes(name: str, inp: dict[str, Any]) -> tuple[bool, str]:
        if name == "write_file":
            return False, deny_reason
        return True, ""

    provider = MockProvider([
        MockProvider.tool_call("write_file", {"path": "out.txt", "content": "x"}),
        _end_turn("ok after denial"),
    ])
    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=deny_writes,
        tool_registry=ToolRegistry(),  # empty — UnknownToolError if reached
        max_turns=5,
    )
    runner.run(task_prompt="write something")

    second_msgs = provider.history[1].messages
    tr_block = second_msgs[-1]["content"]
    assert isinstance(tr_block, list)
    tr = tr_block[0]
    assert tr["type"] == "tool_result"
    assert tr["is_error"] is True
    assert deny_reason in tr["content"]


def test_gate_deny_never_reaches_executor() -> None:
    """(b) Gate deny means executor is NOT invoked (empty registry confirms this).

    If the denied tool had reached ToolExecutor, it would surface the
    UnknownToolError message "not currently registered" instead of the
    gate's reason.  We verify the gate's reason — not the executor error —
    appears in the tool_result content.
    """
    gate_reason = "gate says no"
    executor_marker = "not currently registered"  # what UnknownToolError produces

    provider = MockProvider([
        MockProvider.tool_call("any_tool", {}),
        _end_turn("after denial"),
    ])
    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=lambda name, inp: (False, gate_reason),
        tool_registry=ToolRegistry(),  # empty
        max_turns=5,
    )
    runner.run(task_prompt="task")

    second_msgs = provider.history[1].messages
    tr = second_msgs[-1]["content"][0]
    assert gate_reason in tr["content"]
    assert executor_marker not in tr["content"]


# ---------------------------------------------------------------------------
# (c) max_turns — configurable; for/else "max turns reached" preserved
# ---------------------------------------------------------------------------


def test_max_turns_constructor_configurable() -> None:
    """(c) max_turns param controls the loop limit (stops at 2, not 5)."""
    script = [MockProvider.tool_call("noop", {})] * 5 + [_end_turn()]
    provider = MockProvider(script)

    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=_allow_all,
        tool_registry=_make_registry("noop"),
        max_turns=2,
    )
    result = runner.run(task_prompt="loop task")

    assert result.turn_count == 2
    assert "max turns reached" in result.errors


def test_max_turns_exhausted_for_else_error() -> None:
    """(c) for/else appends 'max turns reached' when loop exhausts."""
    script = [MockProvider.tool_call("noop", {})] * 10
    provider = MockProvider(script)

    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=_allow_all,
        tool_registry=_make_registry("noop"),
        max_turns=3,
    )
    result = runner.run(task_prompt="infinite loop task")

    assert result.turn_count == 3
    assert result.errors == ("max turns reached",)


def test_end_turn_before_max_turns_no_error() -> None:
    """Provider ends turn early — no 'max turns reached' error."""
    provider = MockProvider([_end_turn("finished early")])

    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=_allow_all,
        tool_registry=ToolRegistry(),
        max_turns=10,
    )
    result = runner.run(task_prompt="quick task")

    assert result.turn_count == 1
    assert result.errors == ()


# ---------------------------------------------------------------------------
# Allowed tool — reaches executor, result returned to provider
# ---------------------------------------------------------------------------


def test_allowed_tool_executes_and_result_fed_back() -> None:
    """Allowed tool goes through executor; result appears in second provider call."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="echo",
        description="Echo",
        input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        fn=lambda msg="": f"echo:{msg}",
    ))

    provider = MockProvider([
        MockProvider.tool_call("echo", {"msg": "hello"}),
        _end_turn("received"),
    ])
    runner = ForkedAgentRunner(
        provider=provider,
        system_prompt="sys",
        can_use_tool=_allow_all,
        tool_registry=registry,
        max_turns=5,
    )
    result = runner.run(task_prompt="echo something")

    assert result.errors == ()
    second_msgs = provider.history[1].messages
    tr = second_msgs[-1]["content"][0]
    assert tr["is_error"] is False
    assert "echo:hello" in tr["content"]


# ---------------------------------------------------------------------------
# (d) Write confinement — tested via ExtractMemoriesRunner thin wrapper
# ---------------------------------------------------------------------------


def test_extract_memories_thin_wrapper_writes_confined_to_memory_dir(
    tmp_path: Path,
) -> None:
    """(d) ExtractMemoriesRunner (thin wrapper) writes land inside memory_dir."""
    from simple_coding_agent.extract_memories import ExtractMemoriesRunner

    write_call = MockProvider.tool_call("write_memory_entry", {
        "type": "project",
        "id": "wrap-confinement",
        "name": "Wrapper Confinement Test",
        "description": "Verifies write confinement via thin wrapper",
        "body": "Memory body content",
    })
    provider = MockProvider([write_call, _end_turn("written")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="extract sys",
        base_messages=[],
        tool_registry=_make_registry("read_file", "list_files", "search_text"),
    )
    result = runner.run(new_message_count=2)

    assert result.errors == ()
    assert len(result.written_paths) == 1
    written = Path(result.written_paths[0])
    # File is inside memory_dir, not somewhere else
    assert written.is_relative_to(tmp_path)
    assert written.exists()


def test_extract_memories_thin_wrapper_context_messages_injected(
    tmp_path: Path,
) -> None:
    """(a)+(d) context_messages (base_messages) reach provider via thin wrapper."""
    from simple_coding_agent.extract_memories import ExtractMemoriesRunner

    base = [
        {"role": "user", "content": "user turn"},
        {"role": "assistant", "content": "assistant turn"},
    ]
    provider = MockProvider([_end_turn("no extraction needed")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="sys",
        base_messages=base,
        tool_registry=_make_registry("read_file", "list_files", "search_text"),
    )
    runner.run(new_message_count=2)

    # base_messages (= context_messages) should appear in the first provider call
    first_msgs = provider.history[0].messages
    assert first_msgs[:2] == base
