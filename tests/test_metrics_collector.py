"""Phase C3/C4 tests: MetricsCollector + AgentLoop wiring.

These tests verify that the new `MetricsCollector` records the correct
per-mechanism counters and that `AgentLoop` increments those counters at
each fire site (full compact, snip, microcompact, reactive compact,
externalized bytes, per-turn token estimates). `LoopResult.metrics`
exposes the collector so REPL `/stats` and demos can read it.

Test plan: RUNTIME_ACTIVATION_PLAN.md section 3.3 (metrics).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from simple_coding_agent.compact import (
    CLEARED_TOOL_RESULT_CONTENT,
    ContextCompactor,
    MicroCompactor,
)
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopStatus
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.provider import (
    MockProvider,
    PromptTooLongError,
    ProviderCall,
    ProviderResponse,
    ProviderStreamEvent,
)
from simple_coding_agent.tool_result_store import ToolResultStore
from simple_coding_agent.tools import Tool, ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Local helpers (independent of test_loop.py internals)
# ---------------------------------------------------------------------------


def _build_loop(
    provider: Any,
    *,
    tools: list[Tool] | None = None,
    transcript: Transcript | None = None,
    budget: ContextBudget | None = None,
    compactor: ContextCompactor | None = None,
    microcompactor: MicroCompactor | None = None,
    tool_result_store: ToolResultStore | None = None,
    metrics: MetricsCollector | None = None,
    max_steps: int = 10,
) -> tuple[AgentLoop, Transcript, MetricsCollector]:
    registry = ToolRegistry()
    for tool in tools or []:
        registry.register(tool)
    executor = ToolExecutor(registry)
    real_budget = budget or ContextBudget(
        max_tokens=200_000, reserved_output_tokens=8_192
    )
    real_transcript = transcript or Transcript()
    builder = ContextBuilder(
        budget=real_budget, tool_result_store=tool_result_store,
    )
    real_metrics = metrics if metrics is not None else MetricsCollector()
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=real_transcript,
        context_builder=builder,
        budget=real_budget,
        registry=registry,
        compactor=compactor,
        microcompactor=microcompactor,
        tool_result_store=tool_result_store,
        metrics=real_metrics,
        max_steps=max_steps,
    )
    return loop, real_transcript, real_metrics


def _tool_exchange_messages(
    tool_use_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    result_content: str,
    timestamp: str,
) -> list[Message]:
    return [
        Message(
            uuid=f"asst-{tool_use_id}",
            role=Role.ASSISTANT,
            content=[ToolCall(id=tool_use_id, name=tool_name, input=tool_input)],
            timestamp=timestamp,
            type=MessageType.TOOL_USE,
        ),
        Message(
            uuid=f"user-{tool_use_id}",
            role=Role.USER,
            content=[ToolResult(tool_use_id=tool_use_id, content=result_content)],
            timestamp=timestamp,
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        ),
    ]


class _PromptTooLongScriptedProvider:
    """Provider that interleaves PromptTooLongError with scripted responses."""

    def __init__(
        self,
        script: list[PromptTooLongError | ProviderResponse],
    ) -> None:
        self._script = list(script)
        self._index = 0
        self.history: list[ProviderCall] = []

    def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        item = self._script[self._index]
        self._index += 1
        if isinstance(item, PromptTooLongError):
            raise item
        self.history.append(ProviderCall(
            system=system,
            messages=list(messages),
            tools=list(tools),
            response=item,
        ))
        return item

    def stream_call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Iterator[ProviderStreamEvent]:
        response = self.call(system=system, messages=messages, tools=tools)
        if response.text:
            yield ProviderStreamEvent.text_delta(response.text)
        yield ProviderStreamEvent.done(response)


# ---------------------------------------------------------------------------
# 1. Full-compact counter
# ---------------------------------------------------------------------------


def test_metrics_counts_full_compact_invocations() -> None:
    """Threshold compact on run #1 + reactive compact on run #2 -> counter == 2."""
    provider = _PromptTooLongScriptedProvider([
        MockProvider.direct_answer("first"),
        PromptTooLongError("prompt too long on second turn"),
        MockProvider.direct_answer("recovered"),
    ])
    transcript = Transcript()
    recent_ts = datetime.now(UTC).isoformat()
    for i in range(15):
        for msg in _tool_exchange_messages(
            tool_use_id=f"tu_{i}",
            tool_name="read_file",
            tool_input={"path": f"f_{i}.py"},
            result_content="y" * 1_000,
            timestamp=recent_ts,
        ):
            transcript.append(msg)
        transcript.append(Message(
            uuid=f"asst-text-{i}",
            role=Role.ASSISTANT,
            content=f"observation {i}",
            timestamp=recent_ts,
        ))

    budget = ContextBudget(max_tokens=10_000, reserved_output_tokens=2_000)
    compactor = ContextCompactor(keep_recent=4, compact_threshold=0.5)
    loop, _, metrics = _build_loop(
        provider,
        transcript=transcript,
        budget=budget,
        compactor=compactor,
    )

    result_a = loop.run("first request — should threshold-compact")
    result_b = loop.run("second request — should reactive-compact")

    assert result_a.status == LoopStatus.COMPLETED
    assert result_b.status == LoopStatus.COMPLETED
    assert metrics.full_compacts == 2
    assert metrics.reactive_compacts == 1


# ---------------------------------------------------------------------------
# 2. Snip counter
# ---------------------------------------------------------------------------


def test_metrics_counts_snip_invocations() -> None:
    """A transcript with 3 reads of the same path -> snip fires once."""
    recent_ts = datetime.now(UTC).isoformat()
    transcript = Transcript()
    for i in range(3):
        for msg in _tool_exchange_messages(
            tool_use_id=f"read-{i}",
            tool_name="read_file",
            tool_input={"path": "same.py"},
            result_content=f"body {i}",
            timestamp=recent_ts,
        ):
            transcript.append(msg)

    provider = MockProvider([MockProvider.direct_answer("done")])
    loop, _, metrics = _build_loop(provider, transcript=transcript)

    loop.run("again")

    assert metrics.snip_invocations == 1


# ---------------------------------------------------------------------------
# 3. Microcompact counter
# ---------------------------------------------------------------------------


def test_metrics_counts_microcompact_invocations() -> None:
    """Aged assistant timestamps -> microcompact fires; counter == 1."""
    aged_ts = (datetime.now(UTC) - timedelta(minutes=120)).isoformat()
    transcript = Transcript()
    transcript.append(Message(
        uuid="asst-call",
        role=Role.ASSISTANT,
        content=[ToolCall(id="tu_old", name="read_file", input={"path": "x.py"})],
        timestamp=aged_ts,
        type=MessageType.TOOL_USE,
    ))
    transcript.append(Message(
        uuid="user-result",
        role=Role.USER,
        content=[ToolResult(tool_use_id="tu_old", content="aged body")],
        timestamp=aged_ts,
        type=MessageType.TOOL_RESULT,
        is_meta=True,
    ))
    transcript.append(Message(
        uuid="asst-final",
        role=Role.ASSISTANT,
        content="aged answer",
        timestamp=aged_ts,
    ))

    provider = MockProvider([MockProvider.direct_answer("ok")])
    # keep_recent=0: clear the single aged result so the cleared sentinel is
    # observable. The MicroCompactor default (keep_recent=5) would preserve a
    # lone result; the invocation counter itself is independent of keep_recent.
    loop, _, metrics = _build_loop(
        provider, transcript=transcript, microcompactor=MicroCompactor(keep_recent=0),
    )

    loop.run("continue")

    sent = str(provider.history[0].messages)
    assert CLEARED_TOOL_RESULT_CONTENT in sent
    assert metrics.microcompact_invocations == 1


# ---------------------------------------------------------------------------
# 4. Reactive-compact counter
# ---------------------------------------------------------------------------


def test_metrics_counts_reactive_compact_invocations() -> None:
    """PromptTooLong on first call then success -> reactive_compacts == 1."""
    provider = _PromptTooLongScriptedProvider([
        PromptTooLongError("prompt too long"),
        MockProvider.direct_answer("recovered"),
    ])
    compactor = ContextCompactor(keep_recent=2, compact_threshold=0.95)
    loop, _, metrics = _build_loop(provider, compactor=compactor)

    result = loop.run("oversize request")

    assert result.status == LoopStatus.COMPLETED
    assert metrics.reactive_compacts == 1


# ---------------------------------------------------------------------------
# 5. Externalized-bytes counter
# ---------------------------------------------------------------------------


def test_metrics_sums_externalized_bytes(tmp_path: Any) -> None:
    """Sum equals actual bytes written by ToolResultStore."""
    store = ToolResultStore(storage_dir=str(tmp_path))
    transcript = Transcript()
    recent_ts = datetime.now(UTC).isoformat()
    sizes = [80_000, 70_000, 60_000]
    for i, size in enumerate(sizes):
        for msg in _tool_exchange_messages(
            tool_use_id=f"big-{i}",
            tool_name="read_file",
            tool_input={"path": f"big_{i}.txt"},
            result_content="Z" * size,
            timestamp=recent_ts,
        ):
            transcript.append(msg)

    provider = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, metrics = _build_loop(
        provider,
        transcript=transcript,
        tool_result_store=store,
    )

    loop.run("look")

    assert metrics.externalized_bytes == sum(sizes)


# ---------------------------------------------------------------------------
# 6. Per-turn token estimate
# ---------------------------------------------------------------------------


def test_metrics_records_token_estimate_per_turn() -> None:
    """One AgentStep -> one entry in metrics.tokens_per_turn."""
    provider = MockProvider([MockProvider.direct_answer("answer")])
    loop, _, metrics = _build_loop(provider)

    result = loop.run("hello")

    assert result.status == LoopStatus.COMPLETED
    assert len(metrics.tokens_per_turn) == len(result.steps)
    for tokens in metrics.tokens_per_turn:
        assert tokens >= 0


# ---------------------------------------------------------------------------
# 7. Fresh AgentLoop -> fresh counters (collector identity not shared)
# ---------------------------------------------------------------------------


def test_metrics_resets_per_loop_instance() -> None:
    """A second AgentLoop with its own collector starts at zero."""
    provider_a = MockProvider([MockProvider.direct_answer("a")])
    loop_a, _, metrics_a = _build_loop(provider_a)
    loop_a.run("first")

    assert metrics_a.tokens_per_turn  # at least one entry

    provider_b = MockProvider([MockProvider.direct_answer("b")])
    loop_b, _, metrics_b = _build_loop(provider_b)

    assert metrics_b is not metrics_a
    assert metrics_b.tokens_per_turn == []
    assert metrics_b.full_compacts == 0
    assert metrics_b.snip_invocations == 0
    assert metrics_b.microcompact_invocations == 0
    assert metrics_b.reactive_compacts == 0
    assert metrics_b.externalized_bytes == 0


# ---------------------------------------------------------------------------
# 8. LoopResult.metrics exposes the collector
# ---------------------------------------------------------------------------


def test_loop_result_exposes_metrics_field() -> None:
    """`result.metrics` returns the same collector AgentLoop is wired with."""
    provider = MockProvider([MockProvider.direct_answer("ok")])
    loop, _, metrics = _build_loop(provider)

    result = loop.run("hi")

    assert result.metrics is metrics
    assert result.metrics.full_compacts >= 0


# ---------------------------------------------------------------------------
# 9. SM compact reuse counter
# ---------------------------------------------------------------------------


def test_sm_compact_reuse_counter() -> None:
    """Warm SM path in _force_compact bumps sm_compact_reuses, not sm_compact_misses."""
    from simple_coding_agent.compact import ContextCompactor, LLMSummarizer
    from simple_coding_agent.context import ContextBudget, ContextBuilder
    from simple_coding_agent.loop import AgentLoop
    from simple_coding_agent.models import Message
    from simple_coding_agent.session_memory_state import _SECTION_NAMES, SessionMemoryState
    from simple_coding_agent.tools import ToolExecutor, ToolRegistry
    from simple_coding_agent.transcript import Transcript

    warm_state = SessionMemoryState(
        sections=tuple((name, f"Content for {name}") for name in _SECTION_NAMES)
    )
    provider = MockProvider([MockProvider.direct_answer("done")])
    transcript = Transcript()
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=8192, reserved_output_tokens=4096)
    builder = ContextBuilder(budget=budget)
    metrics = MetricsCollector()
    compactor = ContextCompactor(keep_recent=0, summarizer=LLMSummarizer(provider))
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        session_memory_enabled=True,
        metrics=metrics,
    )
    loop._session_memory_state = warm_state
    for i in range(3):
        transcript.append(Message.user(f"turn {i}"))
        transcript.append(Message.assistant(f"reply {i}"))

    loop._force_compact()

    assert metrics.sm_compact_reuses == 1
    assert metrics.sm_compact_misses == 0


# ---------------------------------------------------------------------------
# 10. SM compact miss counter
# ---------------------------------------------------------------------------


def test_sm_compact_miss_counter() -> None:
    """SM enabled but cold state in _force_compact bumps sm_compact_misses."""
    from simple_coding_agent.compact import ContextCompactor, RuleBasedSummarizer
    from simple_coding_agent.context import ContextBudget, ContextBuilder
    from simple_coding_agent.loop import AgentLoop
    from simple_coding_agent.models import Message
    from simple_coding_agent.tools import ToolExecutor, ToolRegistry
    from simple_coding_agent.transcript import Transcript

    provider = MockProvider([MockProvider.direct_answer("done")])
    transcript = Transcript()
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=8192, reserved_output_tokens=4096)
    builder = ContextBuilder(budget=budget)
    metrics = MetricsCollector()
    compactor = ContextCompactor(keep_recent=0, summarizer=RuleBasedSummarizer())
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        session_memory_enabled=True,  # enabled but state stays cold (empty)
        metrics=metrics,
    )
    # SM state is empty by default — cold path
    assert loop._session_memory_state.is_empty
    for i in range(3):
        transcript.append(Message.user(f"turn {i}"))
        transcript.append(Message.assistant(f"reply {i}"))

    loop._force_compact()

    assert metrics.sm_compact_misses == 1
    assert metrics.sm_compact_reuses == 0


def test_sm_compact_miss_not_recorded_when_sm_disabled() -> None:
    """When --session-memory is OFF, _force_compact does not bump sm_compact_misses.

    Locks review-fix: previously the metric bumped on every compaction even
    when the user never opted in, conflating "didn't enable feature" with
    "feature was enabled but state was empty". Now the miss counter is only
    recorded when self._sm_enabled is True.
    """
    from simple_coding_agent.compact import ContextCompactor, RuleBasedSummarizer
    from simple_coding_agent.context import ContextBudget, ContextBuilder
    from simple_coding_agent.loop import AgentLoop
    from simple_coding_agent.models import Message
    from simple_coding_agent.tools import ToolExecutor, ToolRegistry
    from simple_coding_agent.transcript import Transcript

    provider = MockProvider([MockProvider.direct_answer("done")])
    transcript = Transcript()
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=8192, reserved_output_tokens=4096)
    builder = ContextBuilder(budget=budget)
    metrics = MetricsCollector()
    compactor = ContextCompactor(keep_recent=0, summarizer=RuleBasedSummarizer())
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        # session_memory_enabled NOT set → defaults to False
        metrics=metrics,
    )
    assert loop._sm_enabled is False
    for i in range(3):
        transcript.append(Message.user(f"turn {i}"))
        transcript.append(Message.assistant(f"reply {i}"))

    loop._force_compact()
    loop._force_compact()  # second compaction should still leave miss at 0

    assert metrics.full_compacts == 2  # both compactions did run
    assert metrics.sm_compact_misses == 0  # but no SM miss recorded
    assert metrics.sm_compact_reuses == 0


# ---------------------------------------------------------------------------
# 11. format_stats includes SM compact lines
# ---------------------------------------------------------------------------


def test_format_stats_includes_sm_compact_lines() -> None:
    """format_stats() must mention sm_compact_reuses and sm_compact_misses."""
    m = MetricsCollector()
    m.record_sm_compact_reuse()
    m.record_sm_compact_miss()
    stats = m.format_stats()
    assert "sm_compact_reuses" in stats
    assert "sm_compact_misses" in stats
