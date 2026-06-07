"""
TodoWrite V1 tool registration.

Source mapping:
  register_todo_write_tool <- TodoWriteTool.ts:65-103 (call body)
                              TodoWriteTool.ts:104-114 (mapToolResultToToolResultBlockParam)
  JSON schema              <- TodoItemSchema in src/utils/todo/types.ts

Design notes:
  - shouldDefer=true (TodoWriteTool.ts:51) is NOT implemented.  The replica
    has no ToolSearch mechanism, so this tool is loaded directly into the
    initial schema (not deferred).  Documented here and in CLAUDE.md Current
    Limitations.
  - verificationNudgeNeeded branch (TodoWriteTool.ts:76-86) is skipped —
    growthbook-gated in TS; no verification agent in this replica.
  - Per-(agentId | sessionId) namespacing (TodoWriteTool.ts:67) is skipped —
    single-agent replica, _todos is one instance field in AgentLoop.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .todo import TodoItem, TodoStatus
from .tools import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# Tool description (mirrors DESCRIPTION in TodoWriteTool/prompt.ts)
# ---------------------------------------------------------------------------

_DESCRIPTION = (
    "Update the todo list for the current session. To be used proactively "
    "and often to track progress and pending tasks. Make sure that at least "
    "one task is in_progress at all times. Always provide both content "
    "(imperative) and activeForm (present continuous) for each task."
)

# ---------------------------------------------------------------------------
# JSON schema for the todo_write tool input
# ---------------------------------------------------------------------------

_TODO_WRITE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "todos": {
            "type": "array",
            "description": "The updated todo list",
            "items": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Imperative form of the task (e.g. 'Fix bug')",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed"],
                    },
                    "activeForm": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Present-continuous form (e.g. 'Fixing bug')",
                    },
                },
                "required": ["content", "status", "activeForm"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["todos"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Success message (verbatim from TodoWriteTool.ts:104-114)
# ---------------------------------------------------------------------------

_SUCCESS_MESSAGE = (
    "Todos have been modified successfully. "
    "Ensure that you continue to use the todo list to track your progress. "
    "Please proceed with the current tasks if applicable"
)


# ---------------------------------------------------------------------------
# Registration factory
# ---------------------------------------------------------------------------

def register_todo_write_tool(
    registry: ToolRegistry,
    get_todos: Callable[[], list[TodoItem]],
    set_todos: Callable[[list[TodoItem]], None],
) -> None:
    """Register the todo_write tool on *registry*.

    get_todos / set_todos are closures over the AgentLoop's _todos field so
    the tool reads and writes the live in-memory list.

    Source: TodoWriteTool.ts:65-103.
    """

    def _todo_write_fn(**kwargs: object) -> str:  # noqa: ANN001
        raw_todos = kwargs.get("todos")
        _validate_todos(raw_todos)
        parsed = _parse_todos(raw_todos)  # type: ignore[arg-type]

        # Mirror TodoWriteTool.ts:69-70: collapse to [] when all done.
        all_done = all(t.status == TodoStatus.COMPLETED for t in parsed)
        set_todos([] if all_done else parsed)
        return _SUCCESS_MESSAGE

    registry.register(Tool(
        name="todo_write",
        description=_DESCRIPTION,
        input_schema=_TODO_WRITE_SCHEMA,
        fn=lambda **kw: _todo_write_fn(**kw),
    ))


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_VALID_STATUSES = frozenset(s.value for s in TodoStatus)


def _validate_todos(raw: object) -> None:
    """Raise ValueError for any schema violation in the todos payload."""
    if not isinstance(raw, list):
        raise ValueError("todos must be a list")
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"todos[{i}] must be an object")
        content = item.get("content")
        if content is None:
            raise ValueError(f"todos[{i}].content is required")
        if not isinstance(content, str):
            raise ValueError(f"todos[{i}].content must be a string")
        if len(content) < 1:
            raise ValueError(f"todos[{i}].content must not be empty")
        status = item.get("status")
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"todos[{i}].status must be one of {sorted(_VALID_STATUSES)}, "
                f"got {status!r}"
            )
        active_form = item.get("activeForm")
        if active_form is None:
            raise ValueError(f"todos[{i}].activeForm is required")
        if not isinstance(active_form, str):
            raise ValueError(f"todos[{i}].activeForm must be a string")
        if len(active_form) < 1:
            raise ValueError(f"todos[{i}].activeForm must not be empty")


def _parse_todos(raw: list[dict[str, Any]]) -> list[TodoItem]:
    return [
        TodoItem(
            content=item["content"],
            status=TodoStatus(item["status"]),
            activeForm=item["activeForm"],
        )
        for item in raw
    ]


__all__ = ["register_todo_write_tool"]
