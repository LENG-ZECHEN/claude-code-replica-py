"""Phase C1: end-to-end stress tests for full-compact, reactive-compact,
SnipTool, and ToolResultStore total-budget caps.

These tests exercise the *integration* of the four context-management
mechanisms that ship in P1-P8 but rarely fire in one-shot CLI runs. They
complement the unit tests under test_compact.py / test_snip.py /
test_tool_result_store.py by composing multiple components inside a real
AgentLoop with a tiny ContextBudget.

Test plan: RUNTIME_ACTIVATION_PLAN.md section 3.3.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from simple_coding_agent.compact import ContextCompactor
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopStatus
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
from simple_coding_agent.snip import SNIPPED_CONTENT
from simple_coding_agent.tool_result_store import (
    DEFAULT_TOTAL_BUDGET_CHARS,
    ToolResultStore,
)
from simple_coding_agent.tools import Tool, ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers (intentionally local — avoid coupling to test_loop.py internals)
# ---------------------------------------------------------------------------

def _build_loop(
    provider: Any,
    *,
    tools: list[Tool] | None = None,
    transcript: Transcript | None = None,
    budget: ContextBudget | None = None,
    compactor: ContextCompactor | None = None,
    tool_result_store: ToolResultStore | None = None,
    max_steps: int = 20,
) -> tuple[AgentLoop, Transcript]:
    registry = ToolRegistry()
    for tool in tools or []:
        registry.register(tool)
    executor = ToolExecutor(registry)
    real_budget = budget or ContextBudget(
        max_tokens=200_000, reserved_output_tokens=8_192
    )
    real_transcript = transcript or Transcript()
    context_builder = ContextBuilder(
        budget=real_budget, tool_result_store=tool_result_store,
    )
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=real_transcript,
        context_builder=context_builder,
        budget=real_budget,
        registry=registry,
        compactor=compactor,
        tool_result_store=tool_result_store,
        max_steps=max_steps,
    )
    return loop, real_transcript


class _PromptTooLongScriptedProvider:
    """Provider that interleaves PromptTooLongError raises with scripted
    responses. Used to drive the reactive-compact retry path."""

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


# ---------------------------------------------------------------------------
# 1. Full-compact fires after large tool results accumulate
# ---------------------------------------------------------------------------

def test_full_compact_fires_after_large_tool_results() -> None:
    transcript = Transcript()
    recent_ts = datetime.now(UTC).isoformat()
    for i in range(15):
        for msg in _tool_exchange_messages(
            tool_use_id=f"tu_{i}",
            tool_name="read_file",
            tool_input={"path": f"f_{i}.py"},
            result_content="x" * 1_000,
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
    provider = MockProvider([MockProvider.direct_answer("summary done")])
    loop, _ = _build_loop(
        provider,
        transcript=transcript,
        budget=budget,
        compactor=compactor,
    )

    result = loop.run("summarize what we've read")

    assert result.status == LoopStatus.COMPLETED
    assert result.compacted is True
    assert result.last_summary is not None
    assert result.last_summary.messages_summarized >= 5
    assert result.last_summary.pre_token_count > result.last_summary.post_token_count


# ---------------------------------------------------------------------------
# 2. Reactive compact on a single PromptTooLong, then succeed
# ---------------------------------------------------------------------------

def test_reactive_compact_on_prompt_too_long() -> None:
    provider = _PromptTooLongScriptedProvider([
        PromptTooLongError("prompt too long"),
        MockProvider.direct_answer("recovered after reactive compact"),
    ])
    compactor = ContextCompactor(keep_recent=2, compact_threshold=0.95)
    loop, _ = _build_loop(provider, compactor=compactor)

    result = loop.run("very large request")

    assert result.status == LoopStatus.COMPLETED
    assert result.answer == "recovered after reactive compact"
    assert result.compacted is True
    assert len(provider.history) == 1


# ---------------------------------------------------------------------------
# 3. Two PromptTooLong errors in a row return MAX_TOKENS without third retry
# ---------------------------------------------------------------------------

def test_reactive_compact_twice_returns_max_tokens() -> None:
    provider = _PromptTooLongScriptedProvider([
        PromptTooLongError("prompt too long once"),
        PromptTooLongError("prompt too long twice"),
    ])
    compactor = ContextCompactor(keep_recent=2, compact_threshold=0.95)
    loop, _ = _build_loop(provider, compactor=compactor)

    result = loop.run("still very large")

    assert result.status == LoopStatus.MAX_TOKENS
    assert result.answer is None
    assert result.compacted is True
    assert len(provider.history) == 0


# ---------------------------------------------------------------------------
# 4. ToolResultStore total-budget cap externalizes oversized results
# ---------------------------------------------------------------------------

def test_tool_result_externalization_total_cap(tmp_path: Any) -> None:
    """5 oversized tool results: per-item externalization keeps inline
    content well below DEFAULT_TOTAL_BUDGET_CHARS (200k) and produces a
    persisted file per result. Verifies the runtime path through
    ContextBuilder._process_tool_results that wires the store into context
    assembly."""
    store = ToolResultStore(storage_dir=str(tmp_path))
    transcript = Transcript()
    recent_ts = datetime.now(UTC).isoformat()
    sizes = [80_000, 70_000, 60_000, 65_000, 75_000]
    for i, size in enumerate(sizes):
        for msg in _tool_exchange_messages(
            tool_use_id=f"big-{i}",
            tool_name="read_file",
            tool_input={"path": f"big_{i}.txt"},
            result_content="X" * size,
            timestamp=recent_ts,
        ):
            transcript.append(msg)

    builder = ContextBuilder(
        budget=ContextBudget(max_tokens=1_000_000, reserved_output_tokens=0),
        tool_result_store=store,
    )
    built = builder.build(transcript=transcript, system="sys")

    assert built.externalized_tool_results == len(sizes)

    inline_total = 0
    persisted_blocks: list[str] = []
    for api_msg in built.messages:
        if isinstance(api_msg["content"], list):
            for block in api_msg["content"]:
                if block.get("type") != "tool_result":
                    continue
                content = block.get("content", "")
                inline_total += len(content)
                if "<persisted-output>" in content:
                    persisted_blocks.append(content)

    assert inline_total <= DEFAULT_TOTAL_BUDGET_CHARS
    assert len(persisted_blocks) == len(sizes)


def test_tool_result_total_budget_externalizes_largest_first(
    tmp_path: Any,
) -> None:
    """Items below the per-item threshold but whose sum exceeds 200k must
    be externalized largest-first until the total drops back under budget."""
    store = ToolResultStore(storage_dir=str(tmp_path))
    sizes = [40_000, 45_000, 48_000, 49_000, 49_500]
    inputs = [(f"id-{i}", "Y" * size) for i, size in enumerate(sizes)]

    outputs = store.process_results_batch(inputs)

    persisted_indices = {
        i for i, (_, stored) in enumerate(outputs) if stored is not None
    }
    assert persisted_indices, "expected the total-budget pass to externalize at least one"

    expected_largest_idx = max(range(len(sizes)), key=lambda i: sizes[i])
    assert expected_largest_idx in persisted_indices

    remaining_inline = sum(
        sizes[i]
        for i, (_, stored) in enumerate(outputs)
        if stored is None
    )
    assert remaining_inline <= DEFAULT_TOTAL_BUDGET_CHARS


# ---------------------------------------------------------------------------
# 5. SnipTool folds redundant read_file results on the same path
# ---------------------------------------------------------------------------

def test_snip_fires_when_same_path_read_three_times() -> None:
    recent_ts = datetime.now(UTC).isoformat()
    transcript = Transcript()
    for i in range(3):
        for msg in _tool_exchange_messages(
            tool_use_id=f"read-{i}",
            tool_name="read_file",
            tool_input={"path": "same.py"},
            result_content=f"read result body {i}",
            timestamp=recent_ts,
        ):
            transcript.append(msg)

    provider = MockProvider([MockProvider.direct_answer("done")])
    loop, _ = _build_loop(provider, transcript=transcript)

    result = loop.run("look at it again")

    assert result.status == LoopStatus.COMPLETED
    sent_context = str(provider.history[0].messages)
    assert sent_context.count(SNIPPED_CONTENT) == 2
    assert "read result body 0" not in sent_context
    assert "read result body 1" not in sent_context
    assert "read result body 2" in sent_context
