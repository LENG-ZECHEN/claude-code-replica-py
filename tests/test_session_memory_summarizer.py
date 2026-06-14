"""TDD tests for SessionMemorySummarizer (M2).

Exit-gate assertions:
  (a) Both test files pass with total growing by ≥12.
  (b) warm-state .summarize() makes ZERO provider calls (MockProvider.history empty).
  (c) cold/empty state delegates to the fallback.
  (d) ContextCompactor(summarizer=SessionMemorySummarizer(prewarmed)) yields a
      CompactSummary with non-empty summary_text.
"""
from __future__ import annotations

from simple_coding_agent.compact import (
    ContextCompactor,
    RuleBasedSummarizer,
    SessionMemorySummarizer,
)
from simple_coding_agent.context import ContextBudget
from simple_coding_agent.models import Message
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.session_memory_state import (
    SessionMemoryState,
    update_session_memory,
)
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_warm_state() -> SessionMemoryState:
    """Return a warm SessionMemoryState with non-trivial content."""
    msgs = [
        Message.user("Implement the login feature"),
        Message.assistant("I'll implement the login feature now."),
    ]
    return update_session_memory(SessionMemoryState.empty(), msgs)


def _make_messages() -> list[Message]:
    return [
        Message.user("Implement the login feature"),
        Message.assistant("I'll implement the login feature now."),
    ]


def _make_big_transcript(n_pairs: int = 30) -> Transcript:
    t = Transcript()
    for i in range(n_pairs):
        t.append(Message.user(f"user turn {i}: do something useful " + "x" * 50))
        t.append(Message.assistant(f"assistant {i}: done " + "y" * 50))
    return t


# ---------------------------------------------------------------------------
# Warm-state fast-path: ZERO provider calls
# ---------------------------------------------------------------------------

def test_warm_state_returns_prewarmed_text() -> None:
    """On a warm state, summarize() must return the pre-accumulated text."""
    warm = _make_warm_state()
    summarizer = SessionMemorySummarizer(state=warm)
    msgs = _make_messages()
    result = summarizer.summarize(msgs)
    assert isinstance(result, str)
    assert len(result) > 0
    # Result matches the rendered state
    assert result == warm.render()


def test_warm_state_makes_zero_provider_calls() -> None:
    """The warm fast-path must not invoke the fallback provider (exit gate (b))."""
    warm = _make_warm_state()
    mock_provider = MockProvider(script=[])

    # Wire a MockProvider-backed LLMSummarizer as the fallback; warm path
    # must short-circuit before it is ever called.
    from simple_coding_agent.compact import LLMSummarizer
    llm_fallback = LLMSummarizer(provider=mock_provider)
    summarizer_with_llm_fallback = SessionMemorySummarizer(
        state=warm, fallback=llm_fallback
    )

    msgs = _make_messages()
    result = summarizer_with_llm_fallback.summarize(msgs)
    # Must have returned without calling the provider
    assert mock_provider.history == [], (
        "warm-state path must make ZERO provider calls, "
        f"but got {len(mock_provider.history)} calls"
    )
    assert len(result) > 0


def test_warm_state_ignores_passed_messages() -> None:
    """On a warm state, the passed messages are NOT used (prewarmed text wins)."""
    warm = _make_warm_state()
    summarizer = SessionMemorySummarizer(state=warm)
    # Pass empty messages — warm path should still return content
    result = summarizer.summarize([])
    assert result == warm.render()


# ---------------------------------------------------------------------------
# Cold-state fallback delegation
# ---------------------------------------------------------------------------

def test_cold_state_delegates_to_rule_based_fallback() -> None:
    """Empty state must delegate to the fallback summarizer (exit gate (c))."""
    cold = SessionMemoryState.empty()
    fallback = RuleBasedSummarizer()
    summarizer = SessionMemorySummarizer(state=cold, fallback=fallback)
    msgs = _make_messages()

    result = summarizer.summarize(msgs)
    expected = fallback.summarize(msgs)
    assert result == expected


def test_cold_state_default_fallback_is_rule_based() -> None:
    """When no fallback is given, cold state uses RuleBasedSummarizer."""
    cold = SessionMemoryState.empty()
    summarizer = SessionMemorySummarizer(state=cold)
    msgs = _make_messages()
    result = summarizer.summarize(msgs)
    # RuleBasedSummarizer produces 9 numbered sections
    assert "1. Primary Request and Intent:" in result


def test_cold_empty_messages_returns_empty() -> None:
    """Cold state + empty messages → fallback returns empty string."""
    cold = SessionMemoryState.empty()
    summarizer = SessionMemorySummarizer(state=cold)
    result = summarizer.summarize([])
    assert result == ""


# ---------------------------------------------------------------------------
# Drop-in for ContextCompactor: produces valid CompactSummary (exit gate (d))
# ---------------------------------------------------------------------------

def test_context_compactor_with_session_memory_summarizer() -> None:
    """ContextCompactor(summarizer=SessionMemorySummarizer(prewarmed)) must
    produce a CompactSummary with non-empty summary_text (exit gate (d))."""
    warm = _make_warm_state()
    summarizer = SessionMemorySummarizer(state=warm)

    # Use a tiny budget so compaction fires immediately
    budget = ContextBudget(max_tokens=2_000, reserved_output_tokens=0)
    compactor = ContextCompactor(summarizer=summarizer, keep_recent=2)

    transcript = _make_big_transcript(n_pairs=10)
    result = compactor.compact(transcript, budget)

    assert result.summary_text, "CompactSummary.summary_text must be non-empty"
    # The summary text is the prewarmed render
    assert result.summary_text == warm.render()


def test_session_memory_summarizer_is_summarizer_protocol() -> None:
    """SessionMemorySummarizer must structurally satisfy the Summarizer Protocol."""

    # Protocol conformance check: the method must exist and match signature
    cold = SessionMemoryState.empty()
    summarizer = SessionMemorySummarizer(state=cold)
    assert hasattr(summarizer, "summarize")
    assert callable(summarizer.summarize)
    # summarize accepts a list[Message] and returns str
    result = summarizer.summarize([])
    assert isinstance(result, str)
