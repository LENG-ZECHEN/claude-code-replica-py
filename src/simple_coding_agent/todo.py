"""
TodoWrite V1 support: status enum, item dataclass, nudge dataclass, and
pure-function helpers used by the turn-based reminder machinery.

Source mapping:
  TodoStatus / TodoItem    <- src/utils/todo/types.ts (19 lines)
  render_todo_nudge_body   <- src/utils/messages.ts:3663-3678 (todo_reminder case)
  count_assistant_turns_since <- src/utils/attachments.ts:3212-3264
  _is_todo_write_call      <- attachments.ts:3233-3242 (tool_use check)
  _is_todo_reminder_attachment <- attachments.ts:3247-3253 (attachment type check)

Design notes:
  - This module is V1 (single-tool, in-memory).  V2 (6-tool Tasks suite with
    file persistence, lockfile concurrency, DAG) is out of scope — see
    TodoWriteTool.ts:51 ``shouldDefer=true`` and TaskCreateTool.ts:69
    ``isEnabled = isTodoV2Enabled()``.
  - TS has two separate constants TURNS_SINCE_WRITE=10 and
    TURNS_BETWEEN_REMINDERS=10 (attachments.ts:254-256).  We collapse them
    into a single TODO_REMINDER_TURNS=10 because both default to the same
    value in TS, trading tuning flexibility for KISS.  This couples the
    "detection" and "cooldown" semantics into one knob; a future split is
    straightforward if needed.
  - shouldDefer=true (TodoWriteTool.ts:51) is not implemented — the replica
    has no ToolSearch mechanism, so the tool is loaded directly into the
    initial schema.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from .models import Message, MessageType, Role

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Mirrors attachments.ts:254-256 TODO_REMINDER_CONFIG (both constants = 10).
# Single value covers both "turns since last write" and "turns between reminders".
TODO_REMINDER_TURNS: int = 10


# ---------------------------------------------------------------------------
# Enums / Dataclasses
# ---------------------------------------------------------------------------

class TodoStatus(StrEnum):
    """Task lifecycle state.  Source: TodoStatusSchema in src/utils/todo/types.ts."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass(frozen=True)
class TodoItem:
    """One task in the session todo list.

    Source: TodoItemSchema in src/utils/todo/types.ts.
    content   -- imperative description (e.g. "Fix bug")
    activeForm -- present-continuous shown during execution (e.g. "Fixing bug")
    """
    content: str      # min length 1
    status: TodoStatus
    activeForm: str   # min length 1


@dataclass(frozen=True)
class TodoNudge:
    """Opaque marker the ContextBuilder consumes to prepend a todo reminder.

    Mirrors the SnipNudge pattern from snip_tool_model.py.
    todos is a snapshot of _todos at arm time so the nudge body is stable
    even if the list changes between arm and inject.
    """
    todos: tuple[TodoItem, ...]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def render_todo_nudge_body(todos: tuple[TodoItem, ...]) -> str:
    """Render the V1 todo reminder text for injection into BuiltContext.

    Source: messages.ts:3663-3678 case 'todo_reminder'.
    The reminder text is reproduced verbatim; callers wrap it in
    <system-reminder> tags.

    When todos is empty, only the reminder text is returned (no echo block).
    This matches the user's stated requirement "严格照 V1（空也 nag）".
    """
    message = (
        "The TodoWrite tool hasn't been used recently. "
        "If you're working on tasks that would benefit from tracking progress, "
        "consider using the TodoWrite tool to track progress. "
        "Also consider cleaning up the todo list if has become stale and no "
        "longer matches what you are working on. "
        "Only use it if it's relevant to the current work. "
        "This is just a gentle reminder - ignore if not applicable. "
        "Make sure that you NEVER mention this reminder to the user"
    )
    if todos:
        items = "\n".join(
            f"{i + 1}. [{todo.status}] {todo.content}"
            for i, todo in enumerate(todos)
        )
        message += f"\n\n\nHere are the existing contents of your todo list:\n\n[{items}]"
    return message


def count_assistant_turns_since(
    messages: list[Message],
    predicate: Callable[[Message], bool],
) -> int:
    """Count assistant turns backwards until predicate fires (exclusive).

    **NOT CALLED IN PRODUCTION** — kept for forward-compat parity tests
    only. The runtime `AgentLoop._maybe_inject_todo_nudge` uses simple
    per-loop integer counters (`_turns_since_last_todo_write` /
    `_turns_since_last_todo_reminder`) instead of transcript scanning;
    see HANDOFF M1 "Counter-based timing" deviation in
    `initiatives/_archive/2026-06-plan-surface/HANDOFF.md`. This helper
    is intentionally excluded from `__all__` so `from todo import *`
    callers do not assume it is the live arm-logic path.

    Source mirror: getTodoReminderTurnCounts() in attachments.ts:3212-3264.

    Rules:
      - Iterate reversed(messages).
      - Count only ASSISTANT-role messages.
      - Skip thinking messages (forward-compat guard; no thinking role today).
      - Stop accumulation when predicate(msg) returns True.
      - The matching message itself does NOT increment the counter — the
        predicate is checked BEFORE the increment (attachments.ts:3231-3232).
    """
    count = 0
    for msg in reversed(messages):
        if msg.role != Role.ASSISTANT:
            # USER / SYSTEM roles don't count; non-assistant attachment types
            # (ATTACHMENT_TODO_NUDGE etc.) are USER-role so they're skipped here.
            # Also check for attachment types that indicate a reminder:
            if predicate(msg):
                break
            continue
        # Skip thinking messages (forward-compat: no thinking role implemented
        # in this replica today, but the guard matches attachments.ts:3226-3228).
        # Thinking messages would carry a special flag; add the check when needed.

        # Check predicate BEFORE incrementing (attachments.ts:3231-3232 comment:
        # "we don't want to count the TodoWrite message itself as '1 turn since write'")
        if predicate(msg):
            break
        count += 1
    return count


# ---------------------------------------------------------------------------
# Predicates used by the arm logic in AgentLoop
# ---------------------------------------------------------------------------

def _is_todo_write_call(msg: Message) -> bool:
    """True iff msg is an ASSISTANT message that called todo_write.

    **NOT CALLED IN PRODUCTION** — paired with `count_assistant_turns_since`
    above for forward-compat parity tests only. Production runtime resets
    `_turns_since_last_todo_write` directly when the `todo_write` tool
    succeeds in `AgentLoop._execute_one`.

    Source mirror: attachments.ts:3233-3242.
    """
    if msg.role != Role.ASSISTANT:
        return False
    if not isinstance(msg.content, list):
        return False
    from .models import ToolCall
    return any(
        isinstance(item, ToolCall) and item.name == "todo_write"
        for item in msg.content
    )


def _is_todo_reminder_attachment(msg: Message) -> bool:
    """True iff msg is an ATTACHMENT_TODO_NUDGE message.

    **NOT CALLED IN PRODUCTION** — paired with `count_assistant_turns_since`
    above for forward-compat parity tests only. Production runtime resets
    `_turns_since_last_todo_reminder` directly when the arm-logic fires
    in `AgentLoop._maybe_inject_todo_nudge`.

    Source mirror: attachments.ts:3247-3253 (checks attachment.type == 'todo_reminder').
    """
    return msg.type == MessageType.ATTACHMENT_TODO_NUDGE


# The three helpers above (count_assistant_turns_since, _is_todo_write_call,
# _is_todo_reminder_attachment) are deliberately NOT exported. They mirror
# the TS transcript-scanning approach to arming the todo reminder, but the
# replica's runtime uses simple per-loop integer counters instead (see
# HANDOFF M1 "Counter-based timing" deviation). The helpers stay defined
# (and explicitly importable via their names) so the parity tests in
# tests/test_todo.py can pin the TS semantics, but `from todo import *`
# will not surface them and reduce the chance of new callers assuming
# they are the live arm-logic path.
__all__ = [
    "TODO_REMINDER_TURNS",
    "TodoItem",
    "TodoNudge",
    "TodoStatus",
    "render_todo_nudge_body",
]
