"""Phase 6 / Step 1: ContextCompactor tests — written before implementation (TDD)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from simple_coding_agent.compact import (
    CLEARED_TOOL_RESULT_CONTENT,
    ContextCompactor,
    LLMSummarizer,
    MicroCompactor,
    RuleBasedSummarizer,
)
from simple_coding_agent.context import (
    ContextBudget,
    _estimate_messages_tokens,
    _normalize_messages,
)
from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(n_pairs: int, content_size: int = 20) -> Transcript:
    t = Transcript()
    for i in range(n_pairs):
        t.append(Message.user(f"user msg {i}: " + "x" * content_size))
        t.append(Message.assistant(f"assistant reply {i}: " + "y" * content_size))
    return t


def _make_tool_exchange(
    tool_use_id: str,
    result_content: str,
    tool_name: str = "read_file",
) -> tuple[Message, Message]:
    tc = ToolCall(id=tool_use_id, name=tool_name, input={"path": "x.py"})
    asst = Message(
        uuid=f"asst-{tool_use_id}",
        role=Role.ASSISTANT,
        content=[tc],
        timestamp="2024-01-01T00:00:00Z",
        type=MessageType.TOOL_USE,
    )
    tr = ToolResult(tool_use_id=tool_use_id, content=result_content)
    user_r = Message(
        uuid=f"user-{tool_use_id}",
        role=Role.USER,
        content=[tr],
        timestamp="2024-01-01T00:00:01Z",
        type=MessageType.TOOL_RESULT,
        is_meta=True,
    )
    return asst, user_r


def _estimate_used(transcript: Transcript) -> int:
    """Token estimate should_compact() sees for the post-boundary messages."""
    messages = transcript.messages_after_compact_boundary()
    return _estimate_messages_tokens(_normalize_messages(messages))


class FakeSummarizer:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[list[Message]] = []

    def summarize(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        return self.output


class _RaisingProvider:
    """Provider double that raises on call()/stream_call() for fallback tests."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def call(
        self,
        system: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> object:
        self.calls += 1
        raise self.exc

    def stream_call(
        self,
        system: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> object:
        self.calls += 1
        raise self.exc


# ---------------------------------------------------------------------------
# should_compact
# ---------------------------------------------------------------------------

def test_should_compact_false_for_empty_transcript() -> None:
    compactor = ContextCompactor()
    budget = ContextBudget(max_tokens=1000, reserved_output_tokens=0)
    assert compactor.should_compact(Transcript(), budget) is False


def test_should_compact_false_when_under_threshold() -> None:
    compactor = ContextCompactor()
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=5_000)
    t = _make_transcript(2)
    assert compactor.should_compact(t, budget) is False


def test_should_compact_true_when_over_threshold() -> None:
    compactor = ContextCompactor(compact_threshold=0.8)
    budget = ContextBudget(max_tokens=100, reserved_output_tokens=0)
    t = _make_transcript(3, content_size=80)
    assert compactor.should_compact(t, budget) is True


def test_should_compact_respects_custom_threshold() -> None:
    # 4 messages with content_size=20 produce ~60 tokens total.
    # budget available=200: tight threshold = 0.1 * 200 = 20 tokens -> fires
    #                        loose threshold = 0.99 * 200 = 198 tokens -> does not fire
    budget = ContextBudget(max_tokens=200, reserved_output_tokens=0)
    t = _make_transcript(2, content_size=20)
    compactor_tight = ContextCompactor(compact_threshold=0.1)
    compactor_loose = ContextCompactor(compact_threshold=0.99)
    assert compactor_tight.should_compact(t, budget) is True
    assert compactor_loose.should_compact(t, budget) is False


# ---------------------------------------------------------------------------
# compact: transcript mutation
# ---------------------------------------------------------------------------

def test_compact_appends_boundary_to_transcript() -> None:
    compactor = ContextCompactor(keep_recent=4)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(5)
    original_len = len(t)
    compactor.compact(t, budget)
    assert len(t) > original_len


def test_compact_boundary_is_last_compact_boundary_type() -> None:
    compactor = ContextCompactor(keep_recent=2)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(4)
    compactor.compact(t, budget)
    boundary_idx = t.last_compact_boundary_index()
    assert boundary_idx >= 0
    assert t.all_messages()[boundary_idx].type == MessageType.COMPACT_BOUNDARY


def test_compact_kept_messages_accessible_after_boundary() -> None:
    compactor = ContextCompactor(keep_recent=4)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(6)  # 12 messages total
    compactor.compact(t, budget)
    post = t.messages_after_compact_boundary()
    non_boundary = [m for m in post if m.type != MessageType.COMPACT_BOUNDARY]
    assert len(non_boundary) == 4


def test_compact_with_fewer_messages_than_keep_recent() -> None:
    """When transcript is smaller than keep_recent, all messages are kept."""
    compactor = ContextCompactor(keep_recent=10)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(2)  # 4 messages < keep_recent=10
    compactor.compact(t, budget)
    post = t.messages_after_compact_boundary()
    non_boundary = [m for m in post if m.type != MessageType.COMPACT_BOUNDARY]
    assert len(non_boundary) == 4


def test_compact_empty_transcript_is_safe() -> None:
    compactor = ContextCompactor(keep_recent=5)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = Transcript()
    result = compactor.compact(t, budget)
    assert result.messages_summarized == 0


# ---------------------------------------------------------------------------
# compact: CompactSummary output
# ---------------------------------------------------------------------------

def test_compact_returns_compact_summary() -> None:
    from simple_coding_agent.models import CompactSummary
    compactor = ContextCompactor(keep_recent=2)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(4)
    result = compactor.compact(t, budget)
    assert isinstance(result, CompactSummary)


def test_compact_summary_messages_summarized_count() -> None:
    compactor = ContextCompactor(keep_recent=4)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(5)  # 10 messages; keep 4 -> summarize 6
    result = compactor.compact(t, budget)
    assert result.messages_summarized == 6


def test_compact_summary_pre_token_count_positive() -> None:
    compactor = ContextCompactor(keep_recent=2)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(3)
    result = compactor.compact(t, budget)
    assert result.pre_token_count > 0


def test_compact_summary_post_less_than_pre() -> None:
    compactor = ContextCompactor(keep_recent=2)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(6)  # 12 messages -> 10 summarized, 2 kept
    result = compactor.compact(t, budget)
    assert result.post_token_count < result.pre_token_count


def test_compact_summary_boundary_uuid_matches_transcript() -> None:
    compactor = ContextCompactor(keep_recent=2)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(3)
    result = compactor.compact(t, budget)
    boundary_idx = t.last_compact_boundary_index()
    boundary_msg = t.all_messages()[boundary_idx]
    assert result.boundary_uuid == boundary_msg.uuid


# ---------------------------------------------------------------------------
# compact: summary text content (rule-based)
# ---------------------------------------------------------------------------

def test_compact_summary_text_includes_user_content() -> None:
    compactor = ContextCompactor(keep_recent=0)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = Transcript()
    t.append(Message.user("Please implement the auth module"))
    t.append(Message.assistant("Sure, I will implement the auth module."))
    result = compactor.compact(t, budget)
    assert "auth module" in result.summary_text


def test_compact_summary_text_includes_tool_call_name() -> None:
    compactor = ContextCompactor(keep_recent=0)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = Transcript()
    asst, user_r = _make_tool_exchange("tc_1", "file content here")
    t.append(asst)
    t.append(user_r)
    result = compactor.compact(t, budget)
    assert "read_file" in result.summary_text


def test_compact_summary_text_is_nonempty_for_nonempty_transcript() -> None:
    compactor = ContextCompactor(keep_recent=0)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(3)
    result = compactor.compact(t, budget)
    assert len(result.summary_text) > 0


def test_compact_summary_text_has_section_headers() -> None:
    compactor = ContextCompactor(keep_recent=0)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(2)
    result = compactor.compact(t, budget)
    assert "Primary Request" in result.summary_text or "User Messages" in result.summary_text


def test_compact_summary_does_not_include_huge_tool_result_inline() -> None:
    """Large tool results are truncated in the summary."""
    compactor = ContextCompactor(keep_recent=0, summary_max_result_chars=50)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = Transcript()
    large_result = "SENSITIVE_DATA_" * 500
    asst, user_r = _make_tool_exchange("tc_big", large_result)
    t.append(asst)
    t.append(user_r)
    result = compactor.compact(t, budget)
    assert large_result not in result.summary_text


# ---------------------------------------------------------------------------
# Summarizer injection
# ---------------------------------------------------------------------------

def test_compact_uses_injected_summarizer() -> None:
    summarizer = FakeSummarizer("fake injected summary")
    compactor = ContextCompactor(keep_recent=0, summarizer=summarizer)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(2)

    result = compactor.compact(t, budget)

    assert result.summary_text == "fake injected summary"
    assert len(summarizer.calls) == 1
    assert len(summarizer.calls[0]) == 4


def test_rule_based_summarizer_produces_nonempty_output() -> None:
    asst, user_r = _make_tool_exchange("tc_summary", "file content here")
    messages = [
        Message.user("Please inspect the file"),
        asst,
        user_r,
        Message.assistant("I inspected the file."),
    ]

    summary = RuleBasedSummarizer().summarize(messages)

    assert summary
    assert "Please inspect the file" in summary
    assert "read_file" in summary


def test_llm_summarizer_parses_tagged_output() -> None:
    provider = MockProvider([
        MockProvider.direct_answer("prefix <summary>Only this summary</summary> suffix")
    ])
    summarizer = LLMSummarizer(provider)

    summary = summarizer.summarize([Message.user("Summarize me")])

    assert summary == "Only this summary"
    assert len(provider.history) == 1


def test_llm_summarizer_no_tags_falls_back_to_rule_based() -> None:
    provider = MockProvider([MockProvider.direct_answer("Plain summary text")])
    fallback = FakeSummarizer("rule-based output")
    summarizer = LLMSummarizer(provider, fallback_summarizer=fallback)

    summary = summarizer.summarize([Message.user("Summarize me")])

    assert summary == "rule-based output"
    assert len(fallback.calls) == 1


def test_llm_summarizer_empty_response_falls_back() -> None:
    provider = MockProvider([MockProvider.direct_answer("")])
    fallback = FakeSummarizer("rule-based output")
    summarizer = LLMSummarizer(provider, fallback_summarizer=fallback)

    summary = summarizer.summarize([Message.user("Summarize me")])

    assert summary == "rule-based output"
    assert len(fallback.calls) == 1


def test_llm_summarizer_empty_tags_falls_back() -> None:
    provider = MockProvider([MockProvider.direct_answer("<summary>   </summary>")])
    fallback = FakeSummarizer("rule-based output")
    summarizer = LLMSummarizer(provider, fallback_summarizer=fallback)

    summary = summarizer.summarize([Message.user("Summarize me")])

    assert summary == "rule-based output"
    assert len(fallback.calls) == 1


def test_llm_summarizer_generic_exception_falls_back() -> None:
    provider = _RaisingProvider(RuntimeError("temporary upstream outage"))
    fallback = FakeSummarizer("rule-based output")
    summarizer = LLMSummarizer(provider, fallback_summarizer=fallback)

    summary = summarizer.summarize([Message.user("Summarize me")])

    assert summary == "rule-based output"
    assert len(fallback.calls) == 1
    assert provider.calls == 1


def test_llm_summarizer_prompt_too_long_reraises() -> None:
    from simple_coding_agent.provider import PromptTooLongError

    provider = _RaisingProvider(PromptTooLongError("input too large"))
    fallback = FakeSummarizer("rule-based output")
    summarizer = LLMSummarizer(provider, fallback_summarizer=fallback)

    with pytest.raises(PromptTooLongError):
        summarizer.summarize([Message.user("Summarize me")])

    assert fallback.calls == []


def test_llm_summarizer_pretrunates_oversized_input() -> None:
    messages: list[Message] = [Message.user("first-user-special-marker")]
    for i in range(1, 30):
        messages.append(Message.assistant(f"middle-{i}-noise"))
    for i in range(30, 50):
        messages.append(Message.assistant(f"recent-{i}-tail"))

    provider = MockProvider([
        MockProvider.direct_answer("<summary>ok</summary>"),
    ])
    summarizer = LLMSummarizer(provider, max_input_tokens=10)

    summary = summarizer.summarize(messages)

    assert summary == "ok"
    assert len(provider.history) == 1
    sent_prompt = str(provider.history[0].messages[0]["content"])
    assert "first-user-special-marker" in sent_prompt
    assert "recent-30-tail" in sent_prompt
    assert "recent-49-tail" in sent_prompt
    assert "middle-15-noise" not in sent_prompt
    # No duplicate prepend of the first user message
    assert sent_prompt.count("first-user-special-marker") == 1


def test_compact_prompt_template_contains_nine_sections() -> None:
    from simple_coding_agent.compact import TEMPLATE_HEAD, TEMPLATE_TAIL

    full = TEMPLATE_HEAD + TEMPLATE_TAIL
    for heading in [
        "1. Primary Request and Intent",
        "2. Key Technical Concepts",
        "3. Files and Code Sections",
        "4. Errors and fixes",
        "5. Problem Solving",
        "6. All user messages",
        "7. Pending Tasks",
        "8. Current Work",
        "9. Optional Next Step",
    ]:
        assert heading in full


# ---------------------------------------------------------------------------
# MicroCompactor
# ---------------------------------------------------------------------------

def test_microcompactor_rejects_zero_minutes() -> None:
    """threshold_minutes < 1 is rejected, mirroring SnipTool(keep_recent=0).

    The aggressive preset uses ``microcompact_minutes=1`` (the floor); a
    value of 0 is nonsensical for a "latest assistant older than N minutes"
    cold-cache check and must fail loudly at construction.
    """
    with pytest.raises(ValueError, match="threshold_minutes must be >= 1"):
        MicroCompactor(threshold_minutes=0)


def test_should_microcompact_false_for_empty_transcript() -> None:
    assert MicroCompactor().should_microcompact([]) is False


def test_should_microcompact_true_when_no_assistant_timestamp() -> None:
    msg = Message(
        uuid="user-no-ts",
        role=Role.USER,
        content="hello",
        timestamp="2024-01-01T00:00:00Z",
    )
    assert MicroCompactor().should_microcompact([msg]) is True


def test_should_microcompact_true_when_latest_assistant_is_old() -> None:
    now = datetime(2024, 1, 1, 2, 0, tzinfo=UTC)
    old_assistant = Message(
        uuid="asst-old",
        role=Role.ASSISTANT,
        content="old",
        timestamp=(now - timedelta(minutes=61)).isoformat(),
    )
    assert MicroCompactor().should_microcompact([old_assistant], now=now) is True


def test_should_microcompact_false_when_latest_assistant_is_recent() -> None:
    now = datetime(2024, 1, 1, 2, 0, tzinfo=UTC)
    recent_assistant = Message(
        uuid="asst-recent",
        role=Role.ASSISTANT,
        content="recent",
        timestamp=(now - timedelta(minutes=10)).isoformat(),
    )
    assert MicroCompactor().should_microcompact([recent_assistant], now=now) is False


def test_microcompact_clears_compactable_tool_results() -> None:
    messages: list[Message] = []
    for tool_name in ("read_file", "run_shell", "search_text", "list_files"):
        asst, user_r = _make_tool_exchange(
            f"tc_{tool_name}",
            f"{tool_name} output",
            tool_name=tool_name,
        )
        messages.extend([asst, user_r])

    # keep_recent=0 reproduces the pre-PDF "clear every compactable result"
    # behaviour. The default is now keep_recent=5 (PDF alignment), under which
    # these 4 results would all be preserved; see test_microcompact_keep_recent_*.
    compacted = MicroCompactor(keep_recent=0).microcompact(messages)
    result_contents = [
        item.content
        for msg in compacted
        if isinstance(msg.content, list)
        for item in msg.content
        if isinstance(item, ToolResult)
    ]

    assert result_contents == [CLEARED_TOOL_RESULT_CONTENT] * 4


def test_microcompact_does_not_clear_non_compactable_tool_result() -> None:
    asst, user_r = _make_tool_exchange("tc_custom", "important output", tool_name="custom_tool")

    compacted = MicroCompactor().microcompact([asst, user_r])
    compacted_content = compacted[1].content

    assert isinstance(compacted_content, list)
    assert isinstance(compacted_content[0], ToolResult)
    assert compacted_content[0].content == "important output"


def test_microcompact_returns_new_list_and_does_not_mutate_original() -> None:
    asst, user_r = _make_tool_exchange("tc_mut", "original output")
    original_messages = [asst, user_r]

    # keep_recent=0: the single result is cleared (pre-PDF behaviour).
    compacted = MicroCompactor(keep_recent=0).microcompact(original_messages)

    assert compacted is not original_messages
    assert compacted[1] is not user_r
    original_content = user_r.content
    compacted_content = compacted[1].content
    assert isinstance(original_content, list)
    assert isinstance(compacted_content, list)
    assert isinstance(original_content[0], ToolResult)
    assert isinstance(compacted_content[0], ToolResult)
    assert original_content[0].content == "original output"
    assert compacted_content[0].content == CLEARED_TOOL_RESULT_CONTENT


def test_microcompact_preserves_message_order_and_structure() -> None:
    asst, user_r = _make_tool_exchange("tc_order", "output")
    user_msg = Message.user("next request")
    messages = [asst, user_r, user_msg]

    compacted = MicroCompactor().microcompact(messages)

    assert [msg.uuid for msg in compacted] == [msg.uuid for msg in messages]
    assert compacted[0].type == MessageType.TOOL_USE
    assert compacted[1].type == MessageType.TOOL_RESULT
    assert compacted[2].role == Role.USER
    assert isinstance(compacted[0].content, list)
    assert isinstance(compacted[0].content[0], ToolCall)


def test_microcompact_pairs_tool_result_by_tool_use_id() -> None:
    compactable_asst, compactable_result = _make_tool_exchange(
        "tc_same_position_wrong_order",
        "read output",
        tool_name="read_file",
    )
    custom_asst, custom_result = _make_tool_exchange(
        "tc_custom_pair",
        "custom output",
        tool_name="custom_tool",
    )
    messages = [custom_asst, compactable_asst, compactable_result, custom_result]

    # keep_recent=0: the lone compactable result is cleared (pre-PDF behaviour).
    compacted = MicroCompactor(keep_recent=0).microcompact(messages)
    first_result_content = compacted[2].content
    second_result_content = compacted[3].content

    assert isinstance(first_result_content, list)
    assert isinstance(second_result_content, list)
    assert isinstance(first_result_content[0], ToolResult)
    assert isinstance(second_result_content[0], ToolResult)
    assert first_result_content[0].content == CLEARED_TOOL_RESULT_CONTENT
    assert second_result_content[0].content == "custom output"


def test_microcompact_leaves_unpaired_tool_result_unchanged() -> None:
    user_r = Message(
        uuid="user-unpaired",
        role=Role.USER,
        content=[ToolResult(tool_use_id="missing_tool_use", content="unpaired output")],
        timestamp="2024-01-01T00:00:01Z",
        type=MessageType.TOOL_RESULT,
        is_meta=True,
    )

    compacted = MicroCompactor().microcompact([user_r])
    compacted_content = compacted[0].content

    assert isinstance(compacted_content, list)
    assert isinstance(compacted_content[0], ToolResult)
    assert compacted_content[0].content == "unpaired output"


def test_microcompact_handles_conflicting_duplicate_tool_use_ids_conservatively() -> None:
    first_asst, user_r = _make_tool_exchange(
        "tc_duplicate",
        "duplicate output",
        tool_name="read_file",
    )
    second_asst = Message(
        uuid="asst-duplicate-custom",
        role=Role.ASSISTANT,
        content=[ToolCall(id="tc_duplicate", name="custom_tool", input={})],
        timestamp="2024-01-01T00:00:02Z",
        type=MessageType.TOOL_USE,
    )

    compacted = MicroCompactor().microcompact([first_asst, second_asst, user_r])
    compacted_content = compacted[2].content

    assert isinstance(compacted_content, list)
    assert isinstance(compacted_content[0], ToolResult)
    assert compacted_content[0].content == "duplicate output"


# ---------------------------------------------------------------------------
# M1 (ctx-pdf): MicroCompactor keep_recent — preserve the N most recent
# compactable tool_results (PDF §3 "keep latest 5"). Default is 5.
# ---------------------------------------------------------------------------

def _read_file_exchanges(bodies: list[str]) -> list[Message]:
    """One read_file tool_use + tool_result message pair per body, in order."""
    messages: list[Message] = []
    for i, body in enumerate(bodies):
        asst, user_r = _make_tool_exchange(
            f"tc_recent_{i:02d}", body, tool_name="read_file",
        )
        messages.extend([asst, user_r])
    return messages


def _result_contents(messages: list[Message]) -> list[str]:
    """Flatten ToolResult contents in transcript order."""
    return [
        item.content
        for msg in messages
        if isinstance(msg.content, list)
        for item in msg.content
        if isinstance(item, ToolResult)
    ]


def test_microcompact_keep_recent_defaults_to_five() -> None:
    """Default MicroCompactor preserves the 5 most recent compactable results."""
    bodies = [f"body-{i}" for i in range(7)]
    compacted = MicroCompactor().microcompact(_read_file_exchanges(bodies))

    # First 2 (oldest) cleared; last 5 (most recent) preserved untouched.
    assert _result_contents(compacted) == [
        CLEARED_TOOL_RESULT_CONTENT,
        CLEARED_TOOL_RESULT_CONTENT,
        "body-2",
        "body-3",
        "body-4",
        "body-5",
        "body-6",
    ]


def test_microcompact_keep_recent_zero_clears_all() -> None:
    """keep_recent=0 reproduces the pre-PDF clear-everything behaviour."""
    bodies = [f"body-{i}" for i in range(3)]
    compacted = MicroCompactor(keep_recent=0).microcompact(
        _read_file_exchanges(bodies)
    )

    assert _result_contents(compacted) == [CLEARED_TOOL_RESULT_CONTENT] * 3


def test_microcompact_keep_recent_preserves_all_when_fewer_than_keep() -> None:
    """With fewer compactable results than keep_recent, nothing is cleared."""
    bodies = [f"body-{i}" for i in range(3)]
    compacted = MicroCompactor(keep_recent=5).microcompact(
        _read_file_exchanges(bodies)
    )

    assert _result_contents(compacted) == ["body-0", "body-1", "body-2"]


def test_microcompact_keep_recent_custom_value() -> None:
    """keep_recent=2 clears all but the 2 most recent compactable results."""
    bodies = [f"body-{i}" for i in range(5)]
    compacted = MicroCompactor(keep_recent=2).microcompact(
        _read_file_exchanges(bodies)
    )

    assert _result_contents(compacted) == [
        CLEARED_TOOL_RESULT_CONTENT,
        CLEARED_TOOL_RESULT_CONTENT,
        CLEARED_TOOL_RESULT_CONTENT,
        "body-3",
        "body-4",
    ]


def test_microcompact_rejects_negative_keep_recent() -> None:
    with pytest.raises(ValueError, match="keep_recent must be >= 0"):
        MicroCompactor(keep_recent=-1)


# ---------------------------------------------------------------------------
# M1 (ctx-pdf): should_compact double-headroom formula + min_session floor.
# New trigger: used >= max_tokens - output_headroom - compact_headroom
#              AND used >= min_session_tokens.
# Legacy ratio trigger (used > available_tokens * compact_threshold) is
# preserved as a second OR'd trigger.
# ---------------------------------------------------------------------------

def _bulk_transcript(total_chars: int) -> Transcript:
    """Transcript whose serialized size is ~total_chars (alternating roles).

    Alternating user/assistant avoids same-role merge in _normalize_messages,
    so the char count maps cleanly to the token estimate (chars / 4).
    """
    t = Transcript()
    chunk_chars = 1_000
    n = max(1, total_chars // chunk_chars)
    chunk = "z" * chunk_chars
    for i in range(n):
        if i % 2 == 0:
            t.append(Message.user(chunk))
        else:
            t.append(Message.assistant(chunk))
    return t


def test_should_compact_double_headroom_formula_fires() -> None:
    """New formula fires (floor satisfied) while legacy ratio does NOT.

    max_tokens=40_000 -> formula threshold = 40_000 - 12_000 - 20_000 = 8_000.
    used ~= 31_000 tokens >= 8_000 AND >= 30_000 floor -> new trigger fires.
    Legacy: 0.8 * 40_000 = 32_000; used 31_000 is below it, so the legacy
    ratio does NOT fire — isolating the new formula as the cause.
    """
    compactor = ContextCompactor(compact_threshold=0.8)
    budget = ContextBudget(max_tokens=40_000, reserved_output_tokens=0)
    t = _bulk_transcript(124_000)  # ~31_000 tokens

    used = _estimate_used(t)
    assert 30_000 <= used < 32_000, f"fixture drift: used={used}"
    assert compactor.should_compact(t, budget) is True


def test_should_compact_min_session_floor_blocks() -> None:
    """Formula threshold met but min_session floor not met -> no compaction.

    max_tokens=40_000 -> formula threshold = 8_000. used ~= 15_000 tokens is
    >= 8_000 (formula threshold met) but < 30_000 (floor not met), so the new
    trigger is blocked. Legacy 0.8 * 40_000 = 32_000 is also not met.
    """
    compactor = ContextCompactor(compact_threshold=0.8)
    budget = ContextBudget(max_tokens=40_000, reserved_output_tokens=0)
    t = _bulk_transcript(60_000)  # ~15_000 tokens

    used = _estimate_used(t)
    assert 8_000 <= used < 30_000, f"fixture drift: used={used}"
    assert compactor.should_compact(t, budget) is False


def test_should_compact_min_session_floor_releases_when_exceeded() -> None:
    """Crossing the min_session floor flips the new trigger on."""
    compactor = ContextCompactor(compact_threshold=0.99)
    budget = ContextBudget(max_tokens=40_000, reserved_output_tokens=0)
    below = _bulk_transcript(60_000)   # ~15_000 tokens (< 30k floor)
    above = _bulk_transcript(128_000)  # ~32_000 tokens (>= 30k floor)

    # compact_threshold=0.99 keeps the legacy ratio dormant in both cases
    # (0.99 * 40_000 = 39_600), so only the floor governs the outcome.
    assert compactor.should_compact(below, budget) is False
    assert compactor.should_compact(above, budget) is True


def test_should_compact_legacy_ratio_trigger_preserved() -> None:
    """The legacy compact_threshold ratio still fires on a tiny budget.

    The new formula cannot fire here (used is far below the 30_000 floor),
    so a True result proves the legacy second trigger is intact — this is the
    path the aggressive-thresholds preset relies on.
    """
    compactor = ContextCompactor(compact_threshold=0.2)
    budget = ContextBudget(max_tokens=100, reserved_output_tokens=0)
    t = _make_transcript(3, content_size=80)

    used = _estimate_used(t)
    assert used < 30_000  # new formula floor cannot be met
    assert compactor.should_compact(t, budget) is True


def test_should_compact_headrooms_are_configurable() -> None:
    """Custom headrooms shift the formula threshold."""
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _bulk_transcript(140_000)  # ~35_000 tokens
    used = _estimate_used(t)
    assert used >= 30_000

    # Default headrooms: threshold = 200_000 - 32_000 = 168_000 > used -> off.
    assert ContextCompactor(compact_threshold=0.99).should_compact(t, budget) is False
    # Wide headrooms drop the threshold below used -> on (floor also met).
    wide = ContextCompactor(
        compact_threshold=0.99,
        output_headroom=80_000,
        compact_headroom=100_000,
    )
    assert wide.should_compact(t, budget) is True


# ---------------------------------------------------------------------------
# M1 (ctx-pdf): provider-driven default summarizer (PDF §4 "LLM-based").
# ContextCompactor(provider=...) defaults to LLMSummarizer; provider=None
# keeps RuleBasedSummarizer (backward compat). Explicit summarizer wins.
# ---------------------------------------------------------------------------

def test_default_summarizer_with_provider_is_llm() -> None:
    provider = MockProvider([MockProvider.direct_answer("<summary>x</summary>")])
    compactor = ContextCompactor(provider=provider)

    assert isinstance(compactor.summarizer, LLMSummarizer)
    assert compactor.summarizer.provider is provider


def test_default_summarizer_without_provider_is_rule_based() -> None:
    compactor = ContextCompactor()
    assert isinstance(compactor.summarizer, RuleBasedSummarizer)


def test_explicit_summarizer_overrides_provider() -> None:
    provider = MockProvider([MockProvider.direct_answer("<summary>x</summary>")])
    fake = FakeSummarizer("explicit wins")
    compactor = ContextCompactor(provider=provider, summarizer=fake)

    assert compactor.summarizer is fake


def test_provider_summarizer_used_in_compact() -> None:
    """End-to-end: provider-backed default produces the parsed <summary>."""
    provider = MockProvider([
        MockProvider.direct_answer("noise <summary>LLM summary body</summary> end"),
    ])
    compactor = ContextCompactor(keep_recent=0, provider=provider)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=0)
    t = _make_transcript(2)

    result = compactor.compact(t, budget)

    assert result.summary_text == "LLM summary body"
    assert len(provider.history) == 1
