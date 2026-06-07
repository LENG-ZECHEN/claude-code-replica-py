"""
PermissionMode enum, plan-mode teaching text, and PlanModeAttachment marker.

Source mapping:
  PermissionMode      <- toolPermissionContext.mode in src/utils/permissions/permissions.ts
  teaching text       <- mapToolResultToToolResultBlockParam (non-interview path)
                         in src/tools/EnterPlanModeTool/EnterPlanModeTool.ts:103-118
  PlanModeAttachment  <- opaque marker consumed by ContextBuilder per-turn;
                         mirrors SnipNudge / TodoNudge shape established in M4 / M1.

Critical architecture decision (mirrors TS exactly):
  TS does NOT filter tools at the schema layer in plan mode.
  The API `tools` field is identical in NORMAL and PLAN mode.
  Constraint is enforced via two mechanisms:
    (1) per-turn <system-reminder> attachment (the load-bearing lever — ~95%)
    (2) runtime soft-deny in AgentLoop._execute_one (safety net)
  No filter_tools_for_mode or READ_ONLY_TOOLS set here — that coupling lives
  on Tool.read_only (tools.py).

Explicitly NOT implemented:
  - isPlanModeInterviewPhaseEnabled() branch (growthbook-gated, out of scope).
  - USER_TYPE=ant prompt variant (ship "external" variant only).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PermissionMode(StrEnum):
    """Replica of the toolPermissionContext.mode field in TS permissions.ts."""
    NORMAL = "normal"
    PLAN = "plan"


# Single source of truth for the plan-mode teaching text.
# Used both as the enter_plan_mode tool_result content AND as the per-turn
# ATTACHMENT_PLAN_MODE body. Verbatim from EnterPlanModeTool.ts:97-118
# (non-interview-phase path, message + 6-step block).
# Step 4 references AskUserQuestion from TS; no direct equivalent in this
# replica — the line is kept so the model's instructions stay faithful to TS.
ENTER_PLAN_MODE_TEACHING_TEXT: str = (
    "Entered plan mode. You should now focus on exploring the codebase and "
    "designing an implementation approach.\n"
    "\n"
    "In plan mode, you should:\n"
    "1. Thoroughly explore the codebase to understand existing patterns\n"
    "2. Identify similar features and architectural approaches\n"
    "3. Consider multiple approaches and their trade-offs\n"
    "4. Use AskUserQuestion if you need to clarify the approach\n"
    "5. Design a concrete implementation strategy\n"
    "6. When ready, use ExitPlanMode to present your plan for approval\n"
    "\n"
    "Remember: DO NOT write or edit any files yet. This is a read-only "
    "exploration and planning phase."
)


@dataclass(frozen=True)
class PlanModeAttachment:
    """Opaque per-turn marker that tells ContextBuilder to inject the plan-mode
    teaching text as a USER-role <system-reminder> message.

    Carries no state — the teaching text comes from ENTER_PLAN_MODE_TEACHING_TEXT
    (single source of truth). Frozen so it is safe to hash and reuse across
    multiple build() calls within the same turn.

    Source: mirrors SnipNudge (snip_tool_model.py) and TodoNudge (todo.py) shape.
    """


__all__ = ["ENTER_PLAN_MODE_TEACHING_TEXT", "PermissionMode", "PlanModeAttachment"]
