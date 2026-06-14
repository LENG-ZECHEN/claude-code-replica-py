"""M3: tests for session-memory wiring in AgentLoop.

Three test surfaces (required by §2 exit gate):
  1. Stop-hook fold: maybe_update_session_memory fires in _run_stop_hooks and
     keeps SessionMemoryState warm across REPL turns.
  2. Zero-call compaction: warm SM → _force_compact injects
     SessionMemorySummarizer → ZERO extra provider calls.
  3. Cold-SM fallback: cold/empty state → full Rule/LLM compaction, no crash
     (null-vs-throw contract from autoCompact.ts:241).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_coding_agent.compact import ContextCompactor, LLMSummarizer, RuleBasedSummarizer
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.models import Message
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.session_memory_state import _SECTION_NAMES, SessionMemoryState
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_warm_state() -> SessionMemoryState:
    """Return a pre-warmed SessionMemoryState with content in all sections."""
    return SessionMemoryState(
        sections=tuple(
            (name, f"Content for {name}") for name in _SECTION_NAMES
        )
    )


def _make_loop(
    provider: MockProvider,
    *,
    session_memory_enabled: bool = False,
    compactor: ContextCompactor | None = None,
) -> AgentLoop:
    transcript = Transcript()
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=8192, reserved_output_tokens=4096)
    builder = ContextBuilder(budget=budget)
    if compactor is None:
        compactor = ContextCompactor(keep_recent=1)
    return AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        session_memory_enabled=session_memory_enabled,
    )


def _populate_transcript(loop: AgentLoop, n: int = 3) -> None:
    """Add n user+assistant message pairs so compact has something to work with."""
    for i in range(n):
        loop._transcript.append(Message.user(f"turn {i}"))
        loop._transcript.append(Message.assistant(f"reply {i}"))


# ---------------------------------------------------------------------------
# 1. Stop-hook fold tests
# ---------------------------------------------------------------------------


def test_stop_hook_disabled_leaves_state_cold() -> None:
    """When session_memory_enabled=False, _session_memory_state stays empty."""
    provider = MockProvider([MockProvider.direct_answer("hello")])
    loop = _make_loop(provider, session_memory_enabled=False)
    assert loop._session_memory_state.is_empty
    loop.run("what is 2+2?")
    assert loop._session_memory_state.is_empty


def test_stop_hook_updates_state_after_one_turn() -> None:
    """After 1 turn with session_memory_enabled=True, state becomes warm."""
    provider = MockProvider([MockProvider.direct_answer("The answer is 4.")])
    loop = _make_loop(provider, session_memory_enabled=True)
    assert loop._session_memory_state.is_empty
    loop.run("what is 2+2?")
    assert loop._session_memory_state.is_warm


def test_stop_hook_cursor_advances_after_update() -> None:
    """After SM update succeeds, cursor moves to the last message UUID."""
    provider = MockProvider([MockProvider.direct_answer("reply")])
    loop = _make_loop(provider, session_memory_enabled=True)
    assert loop._session_memory_cursor is None
    loop.run("first question")
    # Cursor must have advanced (non-None)
    assert loop._session_memory_cursor is not None


def test_stop_hook_state_accumulates_across_turns() -> None:
    """Second turn's SM update is non-empty (state accumulates)."""
    provider = MockProvider([
        MockProvider.direct_answer("Answer turn 1."),
        MockProvider.direct_answer("Answer turn 2."),
    ])
    loop = _make_loop(provider, session_memory_enabled=True)
    loop.run("turn 1 question")
    state_after_1 = loop._session_memory_state
    assert state_after_1.is_warm

    loop.run("turn 2 question")
    # State must still be warm (not regressed to empty)
    assert loop._session_memory_state.is_warm


def test_subloop_flag_skips_sm_update() -> None:
    """When is_subloop=True, _run_stop_hooks skips SM update."""
    provider = MockProvider([MockProvider.direct_answer("sub-loop reply")])
    transcript = Transcript()
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=8192, reserved_output_tokens=4096)
    builder = ContextBuilder(budget=budget)
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        session_memory_enabled=True,
        is_subloop=True,
    )
    loop.run("sub-loop question")
    # is_subloop=True must block SM update
    assert loop._session_memory_state.is_empty


# ---------------------------------------------------------------------------
# 2. Zero-call compaction tests (exit-gate load-bearing assertions)
# ---------------------------------------------------------------------------


def test_warm_sm_compaction_zero_extra_provider_calls() -> None:
    """Warm SM → _force_compact makes ZERO extra provider calls.

    This is the core SM-compact value proposition: the summarization step
    is free (returns state.render() immediately, O(0) provider calls).

    Source: sessionMemoryCompact.ts:498 — "SM-compact has no compact-API-call".
    """
    # Use LLMSummarizer as the compactor's default so cold-path would add ≥1 call.
    provider = MockProvider([
        MockProvider.direct_answer("The answer is 4."),
        # Extra answers scripted in case of compaction fallback (cold path)
        MockProvider.direct_answer("compact summary"),
    ])
    compactor = ContextCompactor(
        keep_recent=0,
        summarizer=LLMSummarizer(provider),
    )
    loop = _make_loop(provider, session_memory_enabled=True, compactor=compactor)

    # Inject a pre-warmed state directly — mirrors state after several stop-hook updates
    loop._session_memory_state = _make_warm_state()

    # Add transcript content so compact has messages to summarize
    _populate_transcript(loop, n=3)

    # Record provider call count before compaction
    pre_count = len(provider.history)

    # Trigger compaction — warm SM must intercept, returning 0 extra calls
    loop._force_compact()

    post_count = len(provider.history)
    assert post_count == pre_count, (
        f"Expected ZERO extra provider calls with warm SM, "
        f"but got {post_count - pre_count} extra call(s). "
        f"The warm SM summarizer must return state.render() without calling provider."
    )


def test_cold_sm_compaction_uses_fallback_no_crash() -> None:
    """Cold/empty SM → _force_compact falls back gracefully, no crash.

    This is the null-vs-throw contract: a cold SM must NOT crash _force_compact,
    it must fall through to the configured Rule/LLM summarizer.

    Source: autoCompact.ts:241 autoCompactIfNeeded — :288 tries SM first,
    :312 full compactConversation on null return.
    """
    provider = MockProvider([
        MockProvider.direct_answer("compact summary here"),
    ])
    compactor = ContextCompactor(keep_recent=0, summarizer=RuleBasedSummarizer())
    loop = _make_loop(provider, session_memory_enabled=True, compactor=compactor)

    # State is cold (empty) by default — no stop-hook updates ran yet
    assert loop._session_memory_state.is_empty

    _populate_transcript(loop, n=3)
    result = loop._force_compact()

    assert result is True
    assert loop._last_summary is not None
    assert loop._last_summary.summary_text is not None  # fallback produced output


def test_sm_disabled_compaction_not_intercepted() -> None:
    """When session_memory_enabled=False, compaction uses the default summarizer."""
    provider = MockProvider([
        MockProvider.direct_answer("compact summary"),
    ])
    compactor = ContextCompactor(keep_recent=0, summarizer=LLMSummarizer(provider))
    loop = _make_loop(provider, session_memory_enabled=False, compactor=compactor)

    # Inject warm state — even if warm, disabled flag must skip SM path
    loop._session_memory_state = _make_warm_state()
    _populate_transcript(loop, n=3)

    pre_count = len(provider.history)
    loop._force_compact()
    post_count = len(provider.history)

    # LLMSummarizer (the fallback) was called since SM is disabled
    assert post_count > pre_count, (
        "Expected the LLM summarizer to be called when session_memory_enabled=False"
    )


# ---------------------------------------------------------------------------
# 3. Persistence round-trip tests
# ---------------------------------------------------------------------------


def test_save_load_round_trips_warm_session_memory_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A warm SessionMemoryState survives save_session → load_session."""
    from simple_coding_agent.session_store import load_session, save_session
    from simple_coding_agent.transcript import Transcript

    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))

    transcript = Transcript()
    warm_state = _make_warm_state()

    path = tmp_path / "test_session.json"
    save_session(path, transcript=transcript, last_summary=None, session_memory_state=warm_state)

    _t, _s, restored_state = load_session(path)
    assert restored_state.is_warm
    assert restored_state.sections == warm_state.sections


def test_load_missing_sm_key_returns_empty_state(tmp_path: Path) -> None:
    """Old session files without 'session_memory_state' key load as empty state."""
    import json

    from simple_coding_agent.session_store import load_session
    from simple_coding_agent.transcript import Transcript

    # Write a session file WITHOUT the session_memory_state key
    transcript = Transcript()
    old_format = {
        "version": 1,
        "transcript": transcript.to_jsonable(),
        "last_summary": None,
        # No "session_memory_state" key — old format
    }
    path = tmp_path / "old_session.json"
    path.write_text(json.dumps(old_format), encoding="utf-8")

    _t, _s, sm_state = load_session(path)
    assert sm_state.is_empty, (
        "Old session files without session_memory_state must load as empty state"
    )
