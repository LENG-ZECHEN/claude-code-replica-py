"""Model-driven ``snip_history`` tool (M4, ctx-mgmt-pdf-align).

Source mapping:
  snip_history tool      <- model-driven SnipTool in PDF §3 ("真删除")
  SnipNudge / nudge body <- shouldNudgeForSnips ("every ~10k tokens") PDF §3

This is the model-facing counterpart to the engine-side ``snip.py``
``SnipTool``. The two surfaces COEXIST: engine snip garbage-collects orphans
and ancient cleared pairs deterministically (M2); this tool lets the model
selectively delete past tool_result messages it no longer needs, by passing
their message uuids.

The model learns those uuids because ``context._normalize_messages()`` wraps
every tool_result message body in ``<msg uuid="...">...</msg>`` (OpenAI Chat
Completions strips arbitrary per-message metadata, so the uuid must live in
the content the model actually reads).

Validation lives in the pure function :func:`evaluate_snip_request` so it is
testable without an AgentLoop; :func:`register_snip_history_tool` wraps it in
a Tool whose ``fn`` captures the live ``Transcript`` by reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Message, MessageType, Role, ToolResult
from .tools import Tool, ToolRegistry
from .transcript import Transcript

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SNIP_KEEP_RECENT_DEFAULT: int = 5

_TOOL_NAME = "snip_history"
_TOOL_DESCRIPTION = (
    "Delete past tool_result messages from the conversation history to free "
    "context space. Each tool_result you have seen is wrapped in "
    "<msg uuid='...'>...</msg>; pass any of those uuids in message_uuids to "
    "remove them. You can only snip past tool_result messages; you cannot "
    "snip your own most recent response, the user's current turn, or any of "
    "the most recent 5 tool_result messages. Refused uuids return an error "
    "describing why; accepted uuids are removed and the call returns "
    "'Snipped <N> messages'."
)
_TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message_uuids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
    },
    "required": ["message_uuids"],
}


# ---------------------------------------------------------------------------
# Public dataclasses / exceptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnipNudge:
    """A request to remind the model that it may call ``snip_history``.

    Immutable so a computed nudge cannot drift between build() and the trace
    site. ``candidate_uuids`` are the currently-snippable tool_result uuids
    (compactable results older than the latest 5).
    """

    candidate_uuids: tuple[str, ...]

    def render(self) -> str:
        """Render the system-reminder body listing the candidate uuids."""
        uuids = ", ".join(self.candidate_uuids)
        return (
            "<system-reminder>Context has grown since the last snip. You may "
            "call the snip_history tool with message_uuids to delete old "
            "tool_result messages you no longer need. Snippable message "
            f"uuids: {uuids}</system-reminder>"
        )


@dataclass(frozen=True)
class SnipOutcome:
    """Result of validating a snip_history request (pure, no mutation)."""

    refused: bool
    reason: str | None = None
    removed_uuids: tuple[str, ...] = ()


class SnipRefusedError(RuntimeError):
    """Raised by the snip_history tool fn so ToolExecutor flags is_error.

    The message is the full ``"snip refused: <reason>"`` string the model sees.
    """


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _is_snippable_tool_result(msg: Message) -> bool:
    """A tool_result-bearing user message: TOOL_RESULT type, is_meta, and a
    non-empty content list of only ToolResult blocks."""
    if msg.type != MessageType.TOOL_RESULT or not msg.is_meta:
        return False
    if not isinstance(msg.content, list) or not msg.content:
        return False
    return all(isinstance(item, ToolResult) for item in msg.content)


def _latest_user_text_index(messages: list[Message]) -> int:
    """Index of the most recent plain user-text message, or -1 if none.

    Messages positionally AFTER this index belong to the current turn and
    cannot be snipped.
    """
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.role == Role.USER and isinstance(msg.content, str):
            return i
    return -1


def _protected_recent_uuids(
    messages: list[Message], keep_recent: int
) -> set[str]:
    """UUIDs of the most recent ``keep_recent`` snippable tool_result messages."""
    snippable = [m.uuid for m in messages if _is_snippable_tool_result(m)]
    if keep_recent <= 0:
        return set()
    return set(snippable[-keep_recent:])


def snippable_candidate_uuids(
    messages: list[Message],
    *,
    keep_recent: int = SNIP_KEEP_RECENT_DEFAULT,
) -> list[str]:
    """Tool_result uuids the model may snip: older than the latest ``keep_recent``
    and positionally before the latest user-text message."""
    cutoff = _latest_user_text_index(messages)
    protected = _protected_recent_uuids(messages, keep_recent)
    candidates: list[str] = []
    for i, msg in enumerate(messages):
        if not _is_snippable_tool_result(msg):
            continue
        if cutoff >= 0 and i > cutoff:
            continue
        if msg.uuid in protected:
            continue
        candidates.append(msg.uuid)
    return candidates


def evaluate_snip_request(
    messages: list[Message],
    message_uuids: list[str],
    *,
    keep_recent: int = SNIP_KEEP_RECENT_DEFAULT,
) -> SnipOutcome:
    """Validate a snip_history request without mutating ``messages``.

    Refuses an empty ``message_uuids`` list (a no-op snip is treated as an
    error so the model gets corrective feedback, not a misleading success).
    Otherwise returns a refusing :class:`SnipOutcome` on the first invalid
    uuid, else an accepting outcome whose ``removed_uuids`` lists the
    (de-duplicated) targets.
    """
    if not message_uuids:
        return SnipOutcome(refused=True, reason="no message_uuids provided")

    by_uuid = {m.uuid: (i, m) for i, m in enumerate(messages)}
    cutoff = _latest_user_text_index(messages)
    protected = _protected_recent_uuids(messages, keep_recent)

    removed: list[str] = []
    seen: set[str] = set()
    for uuid in message_uuids:
        if uuid not in by_uuid:
            return SnipOutcome(refused=True, reason=f"uuid {uuid} not found in transcript")
        index, msg = by_uuid[uuid]
        if not _is_snippable_tool_result(msg):
            return SnipOutcome(
                refused=True,
                reason=f"uuid {uuid} is not a snippable tool_result message",
            )
        if cutoff >= 0 and index > cutoff:
            return SnipOutcome(
                refused=True,
                reason=f"uuid {uuid} is in the current turn and cannot be snipped",
            )
        if uuid in protected:
            return SnipOutcome(
                refused=True,
                reason=(
                    f"uuid {uuid} is among the most recent {keep_recent} "
                    "tool_result messages"
                ),
            )
        if uuid not in seen:
            seen.add(uuid)
            removed.append(uuid)

    return SnipOutcome(refused=False, removed_uuids=tuple(removed))


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_snip_history_tool(
    registry: ToolRegistry,
    transcript: Transcript,
    *,
    keep_recent: int = SNIP_KEEP_RECENT_DEFAULT,
) -> None:
    """Register the ``snip_history`` tool against ``registry``.

    The tool's ``fn`` captures ``transcript`` by reference, so it always acts
    on the live history — including messages appended after registration. On
    a valid request it calls ``transcript.replace_all(filtered)`` and returns
    ``"Snipped <N> messages"``; on refusal it raises :class:`SnipRefusedError`
    (which ``ToolExecutor`` surfaces as an is_error tool_result).
    """

    def _snip_history(message_uuids: list[str]) -> str:
        if not isinstance(message_uuids, list):
            raise SnipRefusedError("snip refused: message_uuids must be a list")
        messages = transcript.all_messages()
        outcome = evaluate_snip_request(messages, message_uuids, keep_recent=keep_recent)
        if outcome.refused:
            raise SnipRefusedError(f"snip refused: {outcome.reason}")
        removed = set(outcome.removed_uuids)
        filtered = [m for m in messages if m.uuid not in removed]
        transcript.replace_all(filtered)
        return f"Snipped {len(outcome.removed_uuids)} messages"

    registry.register(
        Tool(
            name=_TOOL_NAME,
            description=_TOOL_DESCRIPTION,
            input_schema=_TOOL_INPUT_SCHEMA,
            fn=_snip_history,
            read_only=True,
        )
    )


__all__ = [
    "SNIP_KEEP_RECENT_DEFAULT",
    "SnipNudge",
    "SnipOutcome",
    "SnipRefusedError",
    "evaluate_snip_request",
    "register_snip_history_tool",
    "snippable_candidate_uuids",
]
