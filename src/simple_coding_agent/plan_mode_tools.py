"""
EnterPlanMode tool factory (plan-surface M2).
ExitPlanMode tool factory will be added in M3.

Source mapping:
  register_enter_plan_mode_tool  <- EnterPlanModeTool.ts call() + isReadOnly()
                                    src/tools/EnterPlanModeTool/EnterPlanModeTool.ts
  mode_setter closure            <- context.setAppState({ mode: 'plan' })
                                    EnterPlanModeTool.ts:88-94

Design note: registration is external (mirrors register_snip_history_tool and
register_todo_write_tool patterns) so AgentLoop does not hard-depend on the
factory — the tool is wired in _build_repl_loop / tool_registry_factory.
"""

from __future__ import annotations

from collections.abc import Callable

from .permission import ENTER_PLAN_MODE_TEACHING_TEXT, PermissionMode
from .tools import Tool, ToolRegistry

_ENTER_PLAN_MODE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def register_enter_plan_mode_tool(
    registry: ToolRegistry,
    mode_setter: Callable[[PermissionMode], None],
) -> None:
    """Register the enter_plan_mode tool in *registry*.

    The tool:
      - takes no parameters (empty input schema)
      - calls mode_setter(PermissionMode.PLAN) to flip the loop's mode
      - returns ENTER_PLAN_MODE_TEACHING_TEXT verbatim (model reads it in tool_result)
      - is read_only=True (safe to call from inside plan mode; idempotent)

    Source: EnterPlanModeTool.ts call() body + isReadOnly() = true.
    """
    def _enter_plan_mode_fn() -> str:
        mode_setter(PermissionMode.PLAN)
        return ENTER_PLAN_MODE_TEACHING_TEXT

    registry.register(Tool(
        name="enter_plan_mode",
        description=(
            "Requests permission to enter plan mode for complex tasks "
            "requiring exploration and design"
        ),
        input_schema=_ENTER_PLAN_MODE_SCHEMA,
        fn=_enter_plan_mode_fn,
        read_only=True,
    ))


__all__ = ["register_enter_plan_mode_tool"]
