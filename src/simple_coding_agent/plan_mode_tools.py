"""
EnterPlanMode and ExitPlanMode tool factories (plan-surface M2/M3).

Source mapping:
  register_enter_plan_mode_tool  <- EnterPlanModeTool.ts call() + isReadOnly()
                                    src/tools/EnterPlanModeTool/EnterPlanModeTool.ts
  register_exit_plan_mode_tool   <- ExitPlanModeV2Tool.ts core call() + approval path
                                    src/tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts
                                    (read only the approval/rejection branch; the 493
                                     lines include plans.ts persistence, allowedPrompts,
                                     analytics, reentry attachments — all out of scope)
  mode_setter closure            <- context.setAppState({ mode: 'plan'/'normal' })

Design note: registration is external (mirrors register_snip_history_tool and
register_todo_write_tool patterns) so AgentLoop does not hard-depend on the
factories — the tools are wired in _build_repl_loop / tool_registry_factory.
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

_EXIT_PLAN_MODE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "string",
            "minLength": 1,
            "description": "The complete plan text to present for user approval.",
        },
    },
    "required": ["plan"],
    "additionalProperties": False,
}


class PlanRejectedError(RuntimeError):
    """Raised by exit_plan_mode when the user rejects the proposed plan.

    Mirrors SnipRefusedError in snip_tool_model.py — ToolExecutor catches
    all exceptions from fn() and converts them to is_error=True ToolResults,
    so the model sees the rejection message and can refine.
    """


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


def register_exit_plan_mode_tool(
    registry: ToolRegistry,
    mode_setter: Callable[[PermissionMode], None],
    approval_callback: Callable[[str], bool],
) -> None:
    """Register the exit_plan_mode tool in *registry*.

    The tool:
      - takes a required ``plan: str`` (minLength 1) argument
      - calls approval_callback(plan) — typically _confirm_exit_plan in cli.py
      - on approval: calls mode_setter(PermissionMode.NORMAL) and returns approval text
      - on rejection: raises PlanRejectedError → ToolExecutor converts to is_error=True
      - is read_only=True (the tool is state-machine only; it does not write files)

    Source: ExitPlanModeV2Tool.ts core call() + approval/rejection branch.
    Out of scope: plan persistence, allowedPrompts, reentry attachments, analytics.
    """
    def _exit_plan_mode_fn(plan: str) -> str:
        if not isinstance(plan, str) or not plan:
            raise ValueError("exit_plan_mode requires a non-empty 'plan' string")
        if approval_callback(plan):
            mode_setter(PermissionMode.NORMAL)
            return "Plan approved. Exiting plan mode."
        raise PlanRejectedError(
            "Plan rejected by user. Stay in plan mode and refine."
        )

    registry.register(Tool(
        name="exit_plan_mode",
        description=(
            "Submit a proposed plan for user approval and exit plan mode. "
            "The plan text will be displayed for the user to approve or reject."
        ),
        input_schema=_EXIT_PLAN_MODE_SCHEMA,
        fn=_exit_plan_mode_fn,
        read_only=True,
    ))


__all__ = [
    "PlanRejectedError",
    "register_enter_plan_mode_tool",
    "register_exit_plan_mode_tool",
]
