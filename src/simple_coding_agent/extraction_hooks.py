"""extraction_hooks: hasMemoryWritesSince + maybe_extract_memories +
maybe_update_session_memory.

Extracted from loop.py to keep that file under 800 lines.
Called by AgentLoop._run_stop_hooks after every run() / run_stream().

Source mapping:
  hasMemoryWritesSince      <- post-conversation write detector
  maybe_extract_memories    <- 7-layer gated extraction trigger
  maybe_update_session_memory <- incremental SM fold at stop hook (SYNCHRONOUS)

DIVERGENCE from TS (session memory update): the replica has no asyncio loop,
so TS's fire-and-forget background extraction (query.ts:1001
`void executePostSamplingHooks`) becomes a SYNCHRONOUS incremental fold at the
stop hook. Net effect is the same — summarization cost is amortized across turns
so compaction-time reuse is ~O(0) — but the producer is not a separate thread.
This matches the existing pattern for synchronous sideQuery recall in
recall_hooks.py. A thread-backed truly-concurrent updater is NOT required for M3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .coding_tools import WRITE_MEMORY_ENTRY_TOOL_NAME
from .extract_memories import ExtractMemoriesRunner
from .models import Message, Role, ToolCall
from .session_memory_state import SessionMemoryState, update_session_memory

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
    "MemoryUpdateOutcome",
    "hasMemoryWritesSince",
    "maybe_extract_memories",
    "maybe_update_session_memory",
]


# ---------------------------------------------------------------------------
# MemoryUpdateOutcome + maybe_update_session_memory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryUpdateOutcome:
    """Returned by maybe_update_session_memory; used by _run_stop_hooks."""
    ran: bool
    new_state: SessionMemoryState
    new_cursor_uuid: str | None


def _messages_since(messages: list[Message], since_uuid: str | None) -> list[Message]:
    """Return messages that come strictly AFTER the message with since_uuid.

    When since_uuid is None, all messages are returned (cursor never set).
    When since_uuid is not found in the list, all messages are returned
    (conservative fallback — process the full list rather than skip).
    """
    if since_uuid is None:
        return messages
    for i, msg in enumerate(messages):
        if msg.uuid == since_uuid:
            return messages[i + 1:]
    return messages


def maybe_update_session_memory(
    *,
    messages: list[Message],
    since_uuid: str | None,
    state: SessionMemoryState,
    session_memory_enabled: bool,
    is_subloop: bool,
) -> MemoryUpdateOutcome:
    """Synchronous incremental SM fold at the stop hook.

    Gates (short-circuit on first False):
      1. is_subloop         — skip inside extraction sub-loops
      2. session_memory_enabled — user opt-in flag (default OFF)
      3. new_messages exist  — nothing to fold if no messages since cursor

    On any exception the prior state and cursor are preserved (at-least-once
    retry), mirroring the maybe_extract_memories failure contract.

    Source: query.ts:1001 `void executePostSamplingHooks` (TS async background
    path; see DIVERGENCE note in module docstring).
    """
    _no_change = MemoryUpdateOutcome(
        ran=False,
        new_state=state,
        new_cursor_uuid=since_uuid,
    )

    if is_subloop:
        return _no_change
    if not session_memory_enabled:
        return _no_change

    new_messages = _messages_since(messages, since_uuid)
    if not new_messages:
        return _no_change

    new_cursor = new_messages[-1].uuid

    try:
        new_state = update_session_memory(state, new_messages)
        return MemoryUpdateOutcome(
            ran=True,
            new_state=new_state,
            new_cursor_uuid=new_cursor,
        )
    except Exception:
        # At-least-once: do NOT advance cursor on failure (mirrors
        # maybe_extract_memories failure contract at extraction_hooks.py:146).
        return _no_change
