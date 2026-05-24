"""extraction_hooks: hasMemoryWritesSince + maybe_extract_memories.

Extracted from loop.py to keep that file under 800 lines.
Called by AgentLoop._run_stop_hooks after every run() / run_stream().

Source mapping:
  hasMemoryWritesSince <- post-conversation write detector
  maybe_extract_memories <- 7-layer gated extraction trigger
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .coding_tools import WRITE_MEMORY_ENTRY_TOOL_NAME
from .extract_memories import ExtractMemoriesRunner
from .models import Message, Role, ToolCall

if TYPE_CHECKING:
    from .metrics import MetricsCollector
    from .provider import Provider
    from .tools import ToolRegistry


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionHookOutcome:
    """Returned by maybe_extract_memories; used by _run_stop_hooks to update state."""
    ran: bool
    last_memory_message_uuid: str | None
    turns_since_last_extraction: int


# ---------------------------------------------------------------------------
# hasMemoryWritesSince
# ---------------------------------------------------------------------------


def hasMemoryWritesSince(
    messages: list[Message],
    since_uuid: str | None,
) -> bool:
    """Return True if any assistant message AFTER since_uuid called write_memory_entry.

    Scans messages in order. When since_uuid is None the scan begins from the
    very first message (i.e. the cursor has never been set).  The message
    whose uuid matches since_uuid is itself NOT counted — only messages that
    come *after* it in the list are examined.
    """
    if not messages:
        return False

    found_cursor = since_uuid is None
    for msg in messages:
        if msg.uuid == since_uuid:
            found_cursor = True
            continue
        if not found_cursor:
            continue
        if msg.role != Role.ASSISTANT:
            continue
        if not isinstance(msg.content, list):
            continue
        for item in msg.content:
            if isinstance(item, ToolCall) and item.name == WRITE_MEMORY_ENTRY_TOOL_NAME:
                return True
    return False


# ---------------------------------------------------------------------------
# maybe_extract_memories
# ---------------------------------------------------------------------------


def maybe_extract_memories(
    *,
    messages: list[Message],
    base_messages_snapshot: list[dict[str, Any]],
    is_subloop: bool,
    extract_memories_enabled: bool,
    auto_memory_enabled: bool,
    extraction_in_progress: bool,
    last_memory_message_uuid: str | None,
    turns_since_last_extraction: int,
    throttle_n: int,
    provider: Provider,
    memory_dir: Path,
    system_prompt: str,
    tool_registry: ToolRegistry,
    metrics: MetricsCollector,
) -> ExtractionHookOutcome:
    """7-layer gated extraction. Returns updated cursor + throttle state.

    Gates (short-circuit on first False):
      1. is_subloop — skip when already inside an extraction context
      2. extract_memories_enabled — user opt-in flag
      3. auto_memory_enabled — memory store must be configured
      4. extraction_in_progress — re-entrancy guard
      5. hasMemoryWritesSince — agent already wrote this turn, skip
      6. throttle — must have accumulated enough turns since last extraction
      7. run ExtractMemoriesRunner; advance cursor only on success
    """
    _no_change = ExtractionHookOutcome(
        ran=False,
        last_memory_message_uuid=last_memory_message_uuid,
        turns_since_last_extraction=turns_since_last_extraction,
    )

    if is_subloop:
        return _no_change
    if not extract_memories_enabled:
        return _no_change
    if not auto_memory_enabled:
        return _no_change
    if extraction_in_progress:
        return _no_change
    if hasMemoryWritesSince(messages, last_memory_message_uuid):
        return _no_change
    if turns_since_last_extraction < throttle_n:
        return _no_change

    # Gate 7: run the extraction engine
    new_uuid = messages[-1].uuid if messages else last_memory_message_uuid
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=memory_dir,
        system_prompt=system_prompt,
        base_messages=base_messages_snapshot,
        tool_registry=tool_registry,
    )
    try:
        result = runner.run(len(base_messages_snapshot))
        metrics.record_extract_invocation()
        metrics.extract_writes += len(result.written_paths)
        return ExtractionHookOutcome(
            ran=True,
            last_memory_message_uuid=new_uuid,
            turns_since_last_extraction=0,
        )
    except Exception:
        # At-least-once: do NOT advance cursor on failure
        return _no_change


__all__ = [
    "ExtractionHookOutcome",
    "hasMemoryWritesSince",
    "maybe_extract_memories",
]
