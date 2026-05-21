"""P9-M2 / Phase C1: end-to-end stress demo for full-compact and reactive-compact.

Run:
    python examples/stress_demo.py

The unit-tested context-management mechanisms in P1-P8 are unreachable
in a one-shot CLI of <=10 turns. This script drives them deterministically
inside an AgentLoop wired to a tiny ContextBudget so M2's exit-gate
markers appear on stdout:

  - ``compact fired (messages_summarized=N)``
  - ``reactive compact fired (messages_summarized=N)``

No network I/O, no API key, no real shell.

Two scenarios run sequentially:

1. Full compact. A pre-populated transcript with 15 ``read_file`` tool
   exchanges (~14k chars each, ~210k total). The combination of per-item
   externalization and a 10k-token ContextBudget forces ``ContextCompactor``
   to run on the first turn.
2. Reactive compact. A scripted ``PromptTooLongError`` on the first
   provider call triggers ``AgentLoop``'s one-shot reactive-compact
   retry, after which a normal response completes the turn.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from simple_coding_agent.compact import ContextCompactor
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopResult, LoopStatus
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
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

_TOOL_RESULT_CHARS = 14_000
_TOOL_EXCHANGE_COUNT = 15
_TINY_MAX_TOKENS = 10_000
_TINY_RESERVED_OUTPUT_TOKENS = 2_000
_KEEP_RECENT_AFTER_COMPACT = 4
_COMPACT_THRESHOLD = 0.5
_FORCE_COMPACT_THRESHOLD = 0.95
_FORCE_COMPACT_KEEP_RECENT = 2


def _tool_exchange(idx: int, *, result_chars: int, timestamp: str) -> list[Message]:
    """A single (tool_use, tool_result) pair as the agent would record it."""
    tool_use_id = f"tu_{idx:03d}"
    return [
        Message(
            uuid=f"asst-{tool_use_id}",
            role=Role.ASSISTANT,
            content=[ToolCall(
                id=tool_use_id,
                name="read_file",
                input={"path": f"src/module_{idx:03d}.py"},
            )],
            timestamp=timestamp,
            type=MessageType.TOOL_USE,
        ),
        Message(
            uuid=f"user-{tool_use_id}",
            role=Role.USER,
            content=[ToolResult(
                tool_use_id=tool_use_id,
                content="x" * result_chars,
            )],
            timestamp=timestamp,
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        ),
    ]


def _seeded_transcript() -> tuple[Transcript, int]:
    """Build a recent-timestamp transcript with 15 large tool exchanges."""
    transcript = Transcript()
    recent_ts = datetime.now(UTC).isoformat()
    total_chars = 0
    for i in range(_TOOL_EXCHANGE_COUNT):
        for msg in _tool_exchange(
            i, result_chars=_TOOL_RESULT_CHARS, timestamp=recent_ts,
        ):
            transcript.append(msg)
        total_chars += _TOOL_RESULT_CHARS
        transcript.append(Message(
            uuid=f"asst-text-{i}",
            role=Role.ASSISTANT,
            content=f"observation about module_{i:03d}",
            timestamp=recent_ts,
        ))
    return transcript, total_chars


class _PromptTooLongScriptedProvider:
    """Provider that interleaves PromptTooLongError raises with scripted responses.

    Same shape as the helper in tests/test_stress_full_compact.py — intentionally
    duplicated to keep the demo self-contained instead of importing from tests.
    """

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


def _build_loop(
    provider: Any,
    *,
    transcript: Transcript,
    budget: ContextBudget,
    compactor: ContextCompactor,
    max_steps: int = 5,
) -> AgentLoop:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    builder = ContextBuilder(budget=budget)
    return AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        max_steps=max_steps,
    )


def _print_compact_summary(label: str, result: LoopResult) -> None:
    """Emit the M2 exit-gate marker line for one scenario.

    The marker format ``<label> fired (messages_summarized=N)`` is normative
    per RUNTIME_ACTIVATION_PLAN.md section 4; supplementary detail is printed
    on a second line so the marker line stays exact.
    """
    summary = result.last_summary
    if not result.compacted or summary is None:
        print(f"{label}: not fired (status={result.status})")
        return
    print(f"{label} fired (messages_summarized={summary.messages_summarized})")
    print(
        f"[detail] pre_tokens={summary.pre_token_count}, "
        f"post_tokens={summary.post_token_count}"
    )


def _run_full_compact_scenario() -> int:
    print("== Scenario 1: full compact ==")
    transcript, total_chars = _seeded_transcript()
    print(f"[setup] total conversation size: {total_chars:,} chars")
    print(
        f"[setup] ContextBudget(max_tokens={_TINY_MAX_TOKENS}, "
        f"reserved_output_tokens={_TINY_RESERVED_OUTPUT_TOKENS})"
    )

    budget = ContextBudget(
        max_tokens=_TINY_MAX_TOKENS,
        reserved_output_tokens=_TINY_RESERVED_OUTPUT_TOKENS,
    )
    compactor = ContextCompactor(
        keep_recent=_KEEP_RECENT_AFTER_COMPACT,
        compact_threshold=_COMPACT_THRESHOLD,
    )
    provider = MockProvider([MockProvider.direct_answer("summary done")])
    loop = _build_loop(
        provider,
        transcript=transcript,
        budget=budget,
        compactor=compactor,
    )

    result = loop.run("summarize what we have read so far")
    _print_compact_summary("compact", result)
    print(f"[result] status={result.status}, answer={result.answer!r}")
    print()
    return 0 if result.status == LoopStatus.COMPLETED else 1


def _run_reactive_compact_scenario() -> int:
    print("== Scenario 2: reactive compact ==")
    provider = _PromptTooLongScriptedProvider([
        PromptTooLongError("prompt too long: simulated first-call overflow"),
        MockProvider.direct_answer("recovered after reactive compact"),
    ])
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    compactor = ContextCompactor(
        keep_recent=_FORCE_COMPACT_KEEP_RECENT,
        compact_threshold=_FORCE_COMPACT_THRESHOLD,
    )
    loop = _build_loop(
        provider,
        transcript=Transcript(),
        budget=budget,
        compactor=compactor,
    )

    result = loop.run("very large request that the provider rejects once")
    _print_compact_summary("reactive compact", result)
    print(f"[result] status={result.status}, answer={result.answer!r}")
    print()
    return 0 if result.status == LoopStatus.COMPLETED else 1


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="stress_demo",
        description=(
            "Phase C1 stress demo: drives full-compact and reactive-compact "
            "end-to-end so M2's exit-gate stdout markers appear."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    _build_parser().parse_args(argv)
    rc1 = _run_full_compact_scenario()
    rc2 = _run_reactive_compact_scenario()
    return 0 if rc1 == 0 and rc2 == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
