"""
Core data structures for simple_coding_agent.

Source mapping:
  Role / MessageType  <- src/types/message.ts (UserMessage, AssistantMessage, etc.)
  ToolCall            <- tool_use block in AssistantMessage content
  ToolResult          <- tool_result block in UserMessage content
  Message             <- src/types/message.ts (UserMessage | AssistantMessage)
  AgentStep           <- one full query-loop turn in src/query.ts
  CompactSummary      <- CompactionResult in src/services/compact/compact.ts
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_uuid() -> str:
    return str(_uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Role(StrEnum):
    """Message sender role.  Mirrors the role field sent to the Anthropic API."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(StrEnum):
    """Internal message classification.
    TEXT / TOOL_USE / TOOL_RESULT messages reach the API. ATTACHMENT messages
    also reach the API: they carry recent-file re-injection content and are
    serialized as user-role messages (M3). COMPACT_BOUNDARY and SNIP_BOUNDARY
    are internal bookkeeping markers stripped by _normalize_messages(),
    mirroring the filtering in src/utils/messages.ts:normalizeMessagesForAPI().
    """
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    COMPACT_BOUNDARY = "compact_boundary"
    SNIP_BOUNDARY = "snip_boundary"
    ATTACHMENT = "attachment"        # recent-file re-injection; serialized as a user message
    ATTACHMENT_MEMORY = "attachment_memory"  # sideQuery memory injection (M7)
    ATTACHMENT_TODO_NUDGE = "attachment_todo_nudge"  # stale-todo reminder (plan-surface M1)
    ATTACHMENT_PLAN_MODE = "attachment_plan_mode"    # per-turn plan-mode teaching (plan-surface M2)


# ---------------------------------------------------------------------------
# Tool primitives
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """A single tool_use block from an assistant response.

    Source: ToolUseBlock in AssistantMessage content (src/types/message.ts).
    """
    id: str                    # stable tool_use_id; pairs with a matching ToolResult
    name: str                  # registered tool name
    input: dict[str, Any]      # validated input dict


@dataclass
class ToolResult:
    """A single tool_result block returned to the model after execution.

    Source: ToolResultBlockParam in src/utils/toolResultStorage.ts.
    The content field may be replaced with a <persisted-output> reference
    when the result exceeds the externalization threshold (default 50k chars).
    Source constant: maxResultSizeChars in src/Tool.ts.
    """
    tool_use_id: str
    content: str
    is_error: bool = False
    persisted_path: str | None = None   # disk path if externalized
    original_size: int | None = None    # char count before externalization

    def to_api_block(self) -> dict[str, Any]:
        """Convert to Anthropic API tool_result content block."""
        return {
            "type": "tool_result",
            "tool_use_id": self.tool_use_id,
            "content": self.content,
            "is_error": self.is_error,
        }


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """A single message in the conversation transcript.

    Source: UserMessage | AssistantMessage | SystemMessage in src/types/message.ts.

    Key flags (matching source):
      is_virtual  — display-only; must not be sent to the API
      is_meta     — tool_result pairing message (sent to API, but flagged for UI)
      is_compact_summary — this message carries a compaction summary
    """
    uuid: str
    role: Role
    content: str | list[ToolCall | ToolResult]
    timestamp: str
    is_meta: bool = False
    is_virtual: bool = False
    is_compact_summary: bool = False
    type: MessageType = MessageType.TEXT

    # --- Factory helpers ---

    @classmethod
    def user(cls, content: str, **kwargs: Any) -> Message:
        return cls(
            uuid=_new_uuid(),
            role=Role.USER,
            content=content,
            timestamp=_now_iso(),
            **kwargs,
        )

    @classmethod
    def assistant(cls, content: str, **kwargs: Any) -> Message:
        return cls(
            uuid=_new_uuid(),
            role=Role.ASSISTANT,
            content=content,
            timestamp=_now_iso(),
            **kwargs,
        )

    @classmethod
    def compact_boundary(cls, messages_summarized: int = 0) -> Message:
        """Create the fence marker inserted after a full compaction.

        Source: createCompactBoundaryMessage() in src/utils/messages.ts (line 4530).
        The boundary is a SYSTEM-role, COMPACT_BOUNDARY-type message.
        getMessagesAfterCompactBoundary() slices the transcript at this marker.
        """
        return cls(
            uuid=_new_uuid(),
            role=Role.SYSTEM,
            content="Conversation compacted",
            timestamp=_now_iso(),
            type=MessageType.COMPACT_BOUNDARY,
            is_meta=True,
        )

    @classmethod
    def snip_boundary(cls) -> Message:
        """Create the fence marker inserted where engine snip deleted blocks.

        Source: snip_boundary marker in the engine-side SnipTool (PDF §3
        snip "真删除 — 不留占位 + snip_boundary marker"). Like
        compact_boundary(), it is a SYSTEM-role, is_meta=True message that is
        filtered out of API serialization by _normalize_messages().
        """
        return cls(
            uuid=_new_uuid(),
            role=Role.SYSTEM,
            content="History snipped",
            timestamp=_now_iso(),
            type=MessageType.SNIP_BOUNDARY,
            is_meta=True,
        )

    @classmethod
    def attachment(cls, path: str, content: str) -> Message:
        """Create a recent-file re-injection message (M3).

        Source: PDF §4 autoCompact post-restoration "recent files re-inject".
        Unlike compact_boundary()/snip_boundary(), this is a USER-role message
        that DOES reach the API: _normalize_messages() passes ATTACHMENT
        through so the model sees the snapshotted file content without
        re-reading. ContextBuilder.build() emits one per recent FileSnapshot
        immediately after the compact boundary.
        """
        body = f'<recent-files>\n<file path="{path}">{content}</file>\n</recent-files>'
        return cls(
            uuid=_new_uuid(),
            role=Role.USER,
            content=body,
            timestamp=_now_iso(),
            type=MessageType.ATTACHMENT,
            is_meta=True,
        )

    @classmethod
    def attachment_memory(cls, content: str) -> Message:
        """Create a sideQuery memory injection message (M7).

        Carries memory file content wrapped in <system-reminder> tags, injected
        before Provider.call() each turn. USER-role so it reaches the API;
        _coalesce_same_role merges it with adjacent user messages.
        """
        return cls(
            uuid=_new_uuid(),
            role=Role.USER,
            content=content,
            timestamp=_now_iso(),
            type=MessageType.ATTACHMENT_MEMORY,
            is_meta=True,
        )

    @classmethod
    def attachment_todo_nudge(cls, content: str) -> Message:
        """Create a stale-todo reminder injection message (plan-surface M1).

        Carries the V1 todo reminder text wrapped in <system-reminder> tags,
        injected before Provider.call() when the double-AND turn counter fires.
        USER-role so it reaches the API; _coalesce_same_role merges adjacency.
        Source: messages.ts:3663-3678 case 'todo_reminder'.
        """
        return cls(
            uuid=_new_uuid(),
            role=Role.USER,
            content=content,
            timestamp=_now_iso(),
            type=MessageType.ATTACHMENT_TODO_NUDGE,
            is_meta=True,
        )

    @classmethod
    def attachment_plan_mode(cls, content: str) -> Message:
        """Create a per-turn plan-mode teaching injection message (plan-surface M2).

        Carries ENTER_PLAN_MODE_TEACHING_TEXT wrapped in <system-reminder> tags,
        prepended each turn while _permission_mode == PLAN. USER-role so it
        reaches the API; _coalesce_same_role merges adjacency.
        Source: attachments.ts:1186 getPlanModeAttachments + messages.ts:3826
        case 'plan_mode' → getPlanModeInstructions.
        """
        return cls(
            uuid=_new_uuid(),
            role=Role.USER,
            content=content,
            timestamp=_now_iso(),
            type=MessageType.ATTACHMENT_PLAN_MODE,
            is_meta=True,
        )


# ---------------------------------------------------------------------------
# AgentStep
# ---------------------------------------------------------------------------

@dataclass
class AgentStep:
    """Record of one complete agent turn (user input -> assistant response).

    Source: one iteration of queryLoop() in src/query.ts.
    """
    turn: int
    user_message: Message
    assistant_message: Message
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    compacted: bool = False
    memory_injected: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# FileSnapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileSnapshot:
    """Point-in-time capture of a file's content at read_file time (M3).

    Source: the "recent files" set re-injected after autoCompact in
    src/services/compact/compact.ts. Captured live in AgentLoop._execute_one()
    when a read_file call succeeds — BEFORE microcompact/snip can clear or
    fold the in-transcript tool_result — so the content re-attached after
    compaction is the genuine file body, not a cleared placeholder.
    Immutable so a captured snapshot cannot drift after the fact.
    """
    path: str
    content: str
    captured_at: str


# ---------------------------------------------------------------------------
# CompactSummary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompactSummary:
    """Result of a full compaction run.

    Source: CompactionResult in src/services/compact/compact.ts.
    The boundary_uuid links this summary to its Message.compact_boundary() marker.
    Frozen (M3): callers rebind self._last_summary rather than mutate fields.
    recent_file_snapshots carries the FileSnapshots captured before this
    compaction so ContextBuilder.build() can re-attach them.
    """
    boundary_uuid: str
    summary_text: str           # model-generated 9-section summary (<analysis> stripped)
    messages_summarized: int
    pre_token_count: int
    post_token_count: int
    restored_files: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now_iso)
    recent_file_snapshots: tuple[FileSnapshot, ...] = ()
