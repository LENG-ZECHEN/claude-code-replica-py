"""Phase 5: ContextBuilder and ContextBudget tests — written before implementation (TDD)."""

from __future__ import annotations

from simple_coding_agent.context import (
    ContextBudget,
    ContextBuilder,
)
from simple_coding_agent.models import (
    CompactSummary,
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.tool_result_store import (
    PERSISTED_OUTPUT_TAG,
    ToolResultStore,
)
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# ContextBudget
# ---------------------------------------------------------------------------

def test_budget_available_tokens() -> None:
    budget = ContextBudget(max_tokens=1000, reserved_output_tokens=200)
    assert budget.available_tokens == 800


def test_budget_available_when_no_reserved() -> None:
    budget = ContextBudget(max_tokens=500, reserved_output_tokens=0)
    assert budget.available_tokens == 500


def test_budget_over_budget_when_above_available() -> None:
    budget = ContextBudget(max_tokens=100, reserved_output_tokens=20)
    assert budget.is_over_budget(81) is True


def test_budget_not_over_budget_at_limit() -> None:
    budget = ContextBudget(max_tokens=100, reserved_output_tokens=20)
    assert budget.is_over_budget(80) is False


def test_budget_not_over_budget_below_limit() -> None:
    budget = ContextBudget(max_tokens=100, reserved_output_tokens=20)
    assert budget.is_over_budget(50) is False


def test_estimate_tokens_char_heuristic() -> None:
    assert ContextBudget.estimate_tokens("abcd") == 1
    assert ContextBudget.estimate_tokens("a" * 100) == 25
    assert ContextBudget.estimate_tokens("a" * 7) == 1


def test_estimate_tokens_empty_string() -> None:
    assert ContextBudget.estimate_tokens("") == 0


# ---------------------------------------------------------------------------
# ContextBuilder — system prompt construction
# ---------------------------------------------------------------------------

def _large_budget() -> ContextBudget:
    return ContextBudget(max_tokens=200_000, reserved_output_tokens=5_000)


def test_build_system_included_as_is_when_no_extras() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    result = builder.build(t, system="Be helpful.")
    assert result.system == "Be helpful."


def test_build_compact_summary_appended_to_system() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    summary = CompactSummary(
        boundary_uuid="abc",
        summary_text="Primary request: build a tool.",
        messages_summarized=10,
        pre_token_count=5000,
        post_token_count=500,
    )
    result = builder.build(t, system="Be helpful.", compact_summary=summary)
    assert "Be helpful." in result.system
    assert "Primary request: build a tool." in result.system


def test_build_memory_snippets_in_system() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    result = builder.build(
        t, system="sys", memory_snippets=["User prefers Python.", "No emojis."]
    )
    assert "User prefers Python." in result.system
    assert "No emojis." in result.system


def test_build_memory_and_summary_both_in_system() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    summary = CompactSummary(
        boundary_uuid="x",
        summary_text="Pending tasks: write tests.",
        messages_summarized=5,
        pre_token_count=1000,
        post_token_count=100,
    )
    result = builder.build(
        t,
        system="base",
        compact_summary=summary,
        memory_snippets=["key fact"],
    )
    assert "base" in result.system
    assert "Pending tasks: write tests." in result.system
    assert "key fact" in result.system


def test_build_no_extras_returns_bare_system() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    result = builder.build(t, system="clean system")
    assert result.system == "clean system"
    assert result.dropped_message_count == 0
    assert result.externalized_tool_results == 0


# ---------------------------------------------------------------------------
# ContextBuilder — message slicing
# ---------------------------------------------------------------------------

def test_build_empty_transcript_yields_no_messages() -> None:
    builder = ContextBuilder(budget=_large_budget())
    result = builder.build(Transcript(), system="sys")
    assert result.messages == []


def test_build_basic_exchange_preserves_roles() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    t.append(Message.user("hello"))
    t.append(Message.assistant("hi there"))
    result = builder.build(t, system="sys")
    assert len(result.messages) == 2
    assert result.messages[0]["role"] == "user"
    assert result.messages[0]["content"] == "hello"
    assert result.messages[1]["role"] == "assistant"
    assert result.messages[1]["content"] == "hi there"


def test_build_uses_post_compact_slice() -> None:
    """Only messages after the last compact boundary are included."""
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    t.append(Message.user("old pre-compact message"))
    t.append(Message.compact_boundary())
    t.append(Message.user("new message"))
    result = builder.build(t, system="sys")
    assert len(result.messages) == 1
    assert result.messages[0]["content"] == "new message"


def test_build_skips_virtual_messages() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    t.append(Message.user("real"))
    t.append(Message.user("virtual", is_virtual=True))
    t.append(Message.assistant("response"))
    result = builder.build(t, system="sys")
    assert len(result.messages) == 2
    assert result.messages[0]["content"] == "real"


def test_build_compact_boundary_not_in_messages() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    t.append(Message.compact_boundary())
    t.append(Message.user("after boundary"))
    result = builder.build(t, system="sys")
    assert all(m["role"] != "system" for m in result.messages)
    assert len(result.messages) == 1


# ---------------------------------------------------------------------------
# ContextBuilder — tool result handling
# ---------------------------------------------------------------------------

def _make_tool_exchange(tool_use_id: str, content: str) -> tuple[Message, Message]:
    tc = ToolCall(id=tool_use_id, name="read_file", input={"path": "x.py"})
    asst = Message(
        uuid="u-asst",
        role=Role.ASSISTANT,
        content=[tc],
        timestamp="2024-01-01T00:00:00Z",
        type=MessageType.TOOL_USE,
    )
    tr = ToolResult(tool_use_id=tool_use_id, content=content)
    user_r = Message(
        uuid="u-user",
        role=Role.USER,
        content=[tr],
        timestamp="2024-01-01T00:00:01Z",
        type=MessageType.TOOL_RESULT,
        is_meta=True,
    )
    return asst, user_r


def test_build_small_tool_result_inlined() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    asst, user_r = _make_tool_exchange("tc_1", "small output")
    t.append(asst)
    t.append(user_r)
    result = builder.build(t, system="sys")
    assert result.externalized_tool_results == 0
    tool_result_block = result.messages[1]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["content"] == "small output"


def test_build_large_tool_result_replaced_with_pointer(tmp_path: object) -> None:
    # Content must exceed BOTH max_inline_chars (100) AND PREVIEW_CHARS (2000)
    # so the preview is a truncated prefix and not the full content string.
    store = ToolResultStore(max_inline_chars=100, storage_dir=str(tmp_path))
    builder = ContextBuilder(budget=_large_budget(), tool_result_store=store)
    t = Transcript()
    large_content = "x" * 2200  # longer than preview limit
    asst, user_r = _make_tool_exchange("tc_big", large_content)
    t.append(asst)
    t.append(user_r)
    result = builder.build(t, system="sys")
    assert result.externalized_tool_results == 1
    tool_result_block = result.messages[1]["content"][0]
    assert PERSISTED_OUTPUT_TAG in tool_result_block["content"]
    assert large_content not in tool_result_block["content"]  # preview is truncated


def test_build_multiple_tool_results_counted(tmp_path: object) -> None:
    store = ToolResultStore(max_inline_chars=10, storage_dir=str(tmp_path))
    builder = ContextBuilder(budget=_large_budget(), tool_result_store=store)
    t = Transcript()
    for i in range(3):
        asst, user_r = _make_tool_exchange(f"tc_{i}", "x" * 50)
        t.append(asst)
        t.append(user_r)
    result = builder.build(t, system="sys")
    assert result.externalized_tool_results == 3


# ---------------------------------------------------------------------------
# ContextBuilder — budget trimming
# ---------------------------------------------------------------------------

def test_build_no_drops_within_budget() -> None:
    builder = ContextBuilder(budget=_large_budget())
    t = Transcript()
    t.append(Message.user("hello"))
    t.append(Message.assistant("hi"))
    result = builder.build(t, system="")
    assert result.dropped_message_count == 0
    assert len(result.messages) == 2


def test_build_preserves_most_recent_messages() -> None:
    """When budget is tight, newest messages survive."""
    budget = ContextBudget(max_tokens=30, reserved_output_tokens=0)
    builder = ContextBuilder(budget=budget)
    t = Transcript()
    for i in range(5):
        t.append(Message.user(f"old {i}"))
        t.append(Message.assistant(f"reply {i}"))
    t.append(Message.user("newest user"))
    t.append(Message.assistant("newest assistant"))
    result = builder.build(t, system="")
    assert result.messages[-1]["content"] == "newest assistant"
    assert result.messages[-2]["content"] == "newest user"


def test_build_dropped_count_when_over_budget() -> None:
    budget = ContextBudget(max_tokens=30, reserved_output_tokens=0)
    builder = ContextBuilder(budget=budget)
    t = Transcript()
    for i in range(10):
        t.append(Message.user(f"message {i}"))
        t.append(Message.assistant(f"response {i}"))
    result = builder.build(t, system="")
    assert result.dropped_message_count > 0


def test_build_estimated_tokens_within_budget_after_trim() -> None:
    budget = ContextBudget(max_tokens=30, reserved_output_tokens=0)
    builder = ContextBuilder(budget=budget)
    t = Transcript()
    for i in range(10):
        t.append(Message.user(f"message {i}"))
        t.append(Message.assistant(f"response {i}"))
    result = builder.build(t, system="")
    assert not budget.is_over_budget(result.estimated_tokens)


def test_build_removes_orphan_tool_result_after_budget_trim() -> None:
    budget = ContextBudget(max_tokens=80, reserved_output_tokens=0)
    builder = ContextBuilder(budget=budget)
    t = Transcript()
    tc = ToolCall(
        id="tc_orphan",
        name="read_file",
        input={"path": "x" * 500},
    )
    t.append(Message(
        uuid="u-asst",
        role=Role.ASSISTANT,
        content=[tc],
        timestamp="2024-01-01T00:00:00Z",
        type=MessageType.TOOL_USE,
    ))
    t.append(Message(
        uuid="u-user",
        role=Role.USER,
        content=[ToolResult(tool_use_id="tc_orphan", content="small")],
        timestamp="2024-01-01T00:00:01Z",
        type=MessageType.TOOL_RESULT,
        is_meta=True,
    ))

    result = builder.build(t, system="")

    assert result.messages == []
    assert result.dropped_message_count == 1


# ---------------------------------------------------------------------------
# BuiltContext
# ---------------------------------------------------------------------------

def test_built_context_has_budget_reference() -> None:
    budget = _large_budget()
    builder = ContextBuilder(budget=budget)
    result = builder.build(Transcript(), system="sys")
    assert result.budget is budget


def test_built_context_estimated_tokens_positive_with_system() -> None:
    builder = ContextBuilder(budget=_large_budget())
    result = builder.build(Transcript(), system="A" * 400)
    assert result.estimated_tokens == 100  # 400 chars // 4
