"""P9-M2 / Phase C2: end-to-end demo for MicroCompactor's cold-cache cleanup.

Run:
    python examples/microcompact_demo.py          # aged transcript (fires)
    python examples/microcompact_demo.py --fresh  # recent transcript (skipped)

MicroCompactor only triggers when the most recent assistant message is
older than 60 minutes. In one-shot CLI runs this almost never happens —
sessions are short. This demo seeds a Transcript whose timestamps are
backdated by 120 minutes, then runs an AgentLoop so the cold-cache
cleanup fires inside ``AgentLoop._maybe_microcompact()`` exactly as it
would in a real long-running session.

Exit-gate marker (per RUNTIME_ACTIVATION_PLAN.md section 4):

    microcompact fired (results cleared=N)

No network I/O, no API key, no real shell.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from simple_coding_agent.compact import (
    CLEARED_TOOL_RESULT_CONTENT,
    MicroCompactor,
)
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopStatus
from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

_AGED_MINUTES = 120
_TOOL_EXCHANGE_COUNT = 3


class _CallCountingMicroCompactor(MicroCompactor):
    """Wraps MicroCompactor to count cleared ToolResults across one run.

    Increments ``results_cleared`` by the number of ToolResults whose content
    was rewritten to ``CLEARED_TOOL_RESULT_CONTENT`` during ``microcompact()``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.microcompact_calls = 0
        self.results_cleared = 0

    def microcompact(self, messages: list[Message]) -> list[Message]:
        self.microcompact_calls += 1
        before = _count_cleared(messages)
        result = super().microcompact(messages)
        after = _count_cleared(result)
        self.results_cleared += max(0, after - before)
        return result


def _count_cleared(messages: list[Message]) -> int:
    """Count ToolResult blocks whose content equals the microcompact sentinel."""
    count = 0
    for msg in messages:
        if not isinstance(msg.content, list):
            continue
        for item in msg.content:
            if isinstance(item, ToolResult) and item.content == CLEARED_TOOL_RESULT_CONTENT:
                count += 1
    return count


def _aged_tool_exchange(idx: int, *, timestamp: str) -> list[Message]:
    tool_use_id = f"tu_aged_{idx:02d}"
    return [
        Message(
            uuid=f"asst-{tool_use_id}",
            role=Role.ASSISTANT,
            content=[ToolCall(
                id=tool_use_id,
                name="read_file",
                input={"path": f"src/old_module_{idx:02d}.py"},
            )],
            timestamp=timestamp,
            type=MessageType.TOOL_USE,
        ),
        Message(
            uuid=f"user-{tool_use_id}",
            role=Role.USER,
            content=[ToolResult(
                tool_use_id=tool_use_id,
                content=f"large file body {idx} (would be cleared by microcompact)",
            )],
            timestamp=timestamp,
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        ),
    ]


def _seeded_transcript(aged_minutes: int) -> tuple[Transcript, int]:
    """Build a transcript whose timestamps are ``aged_minutes`` in the past."""
    transcript = Transcript()
    timestamp = (datetime.now(UTC) - timedelta(minutes=aged_minutes)).isoformat()
    for i in range(_TOOL_EXCHANGE_COUNT):
        for msg in _aged_tool_exchange(i, timestamp=timestamp):
            transcript.append(msg)
    transcript.append(Message(
        uuid="asst-aged-final",
        role=Role.ASSISTANT,
        content="prior turn final answer",
        timestamp=timestamp,
    ))
    return transcript, aged_minutes


def _build_loop(
    transcript: Transcript,
    microcompactor: MicroCompactor,
    provider: MockProvider,
) -> AgentLoop:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    builder = ContextBuilder(budget=budget)
    return AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        microcompactor=microcompactor,
        max_steps=5,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="microcompact_demo",
        description=(
            "Phase C2 microcompact demo: drives MicroCompactor end-to-end "
            "via a backdated transcript so M2's exit-gate marker appears."
        ),
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help=(
            "Seed timestamps at 'now' instead of 120 minutes in the past. "
            "MicroCompactor should skip on this transcript."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    aged_minutes = 0 if args.fresh else _AGED_MINUTES

    print("== Microcompact demo ==")
    transcript, aged = _seeded_transcript(aged_minutes)
    print(
        f"[setup] transcript: {_TOOL_EXCHANGE_COUNT} read_file exchanges, "
        f"assistant message aged: {aged} min"
    )

    counter = _CallCountingMicroCompactor()
    provider = MockProvider([MockProvider.direct_answer("continuation done")])
    loop = _build_loop(transcript, counter, provider)

    result = loop.run("continue the prior work")

    if counter.microcompact_calls > 0 and counter.results_cleared > 0:
        print(f"microcompact fired (results cleared={counter.results_cleared})")
    else:
        print("microcompact skipped: assistant message still fresh (<60 min)")

    print(f"[result] status={result.status}, answer={result.answer!r}")
    return 0 if result.status == LoopStatus.COMPLETED else 1


if __name__ == "__main__":
    raise SystemExit(main())
