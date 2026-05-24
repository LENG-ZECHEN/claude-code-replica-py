"""recall_hooks.py — sideQuery memory injection orchestration (M7).

Extracted from loop.py (mirrors the M5 extraction_hooks.py pattern) so that
loop.py stays ≤800 lines.  The single public function `inject_memory_attachments`
is called once per user turn, before Provider.call(), in both AgentLoop.run()
and AgentLoop.run_stream().

Source mapping:
  inject_memory_attachments <- sideQuery orchestration in src/query.ts / memdir.ts
"""

from __future__ import annotations

from pathlib import Path

from .memdir import (
    collect_recent_successful_tools,
    find_relevant_memories,
    read_memories_for_surfacing,
)
from .models import Message, Role
from .provider import Provider
from .trace import Tracer
from .transcript import Transcript


def inject_memory_attachments(
    transcript: Transcript,
    query: str,
    provider: Provider,
    memory_dir: Path | None,
    auto_memory_enabled: bool,
    already_surfaced: set[str],
    session_bytes_used: int,
    tracer: Tracer,
) -> int:
    """Find and inject relevant memories into *transcript* before Provider.call().

    Returns the updated session_bytes_used.  Mutates *already_surfaced* in-place
    with the ids of newly injected memories.  Never raises — selector failures
    fall back to Jaccard inside find_relevant_memories.
    """
    if not auto_memory_enabled or memory_dir is None:
        return session_bytes_used

    messages = transcript.all_messages()
    # The loop appends the current turn's user input BEFORE injecting, so the
    # last message is that input.  "Recently-used tools" must reflect the
    # PREVIOUS assistant turn, so exclude a trailing user-text message before
    # scanning (otherwise collect_recent_successful_tools stops immediately and
    # always returns []).
    if (
        messages
        and messages[-1].role == Role.USER
        and isinstance(messages[-1].content, str)
    ):
        scan_messages = messages[:-1]
    else:
        scan_messages = messages
    recent_tools = collect_recent_successful_tools(scan_messages)

    result = find_relevant_memories(
        query, memory_dir, provider,
        already_surfaced=already_surfaced,
        recent_tools=recent_tools,
        session_bytes_used=session_bytes_used,
        auto_memory_enabled=auto_memory_enabled,
    )

    tracer.emit(
        "memory_select",
        fallback_used=result.fallback_used,
        manifest_size=result.manifest_size,
        selected_count=len(result.headers),
        session_bytes_used=session_bytes_used,
    )

    if not result.headers:
        return session_bytes_used

    texts = read_memories_for_surfacing(result.headers)
    for header, text in zip(result.headers, texts, strict=True):
        content = f"<system-reminder>\n{text}\n</system-reminder>"
        transcript.append(Message.attachment_memory(content))
        already_surfaced.add(header.id)
        session_bytes_used += len(content)

    return session_bytes_used


__all__ = ["inject_memory_attachments"]
