"""
ContextBuilder and ContextBudget: assemble the API payload for each queryLoop turn.

Source mapping:
  ContextBudget        <- token budget arithmetic in src/query.ts queryLoop()
  ContextBuilder.build <- queryLoop() per-iteration pipeline:
                          getMessagesAfterCompactBoundary() -> tool-result replacement
                          -> message snipping -> normalize -> system prompt assembly
  estimate_tokens      <- roughTokenCountEstimationForMessages() src/utils/messages.ts
                          heuristic: len(text) // 4  (chars-per-token approximation)
  system prompt inject <- memory + compact summary injection in src/query.ts
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .claude_md import ClaudeMdLoader
from .memory import ProjectMemory
from .models import CompactSummary, Message, MessageType, Role, ToolCall, ToolResult
from .permission import ENTER_PLAN_MODE_TEACHING_TEXT, PlanModeAttachment
from .snip_tool_model import SnipNudge
from .todo import TodoNudge, render_todo_nudge_body
from .tool_result_store import ToolResultStore
from .trace import NullTracer, Tracer
from .transcript import Transcript

# ---------------------------------------------------------------------------
# Memory Management teaching section (M3, auto-memory-overhaul)
# Fully static — no f-string — so the prefix is cache-stable across turns.
# Inserted only when project_memory is wired into ContextBuilder.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Todo Management teaching section (plan-surface M1)
# Verbatim from TodoWriteTool/prompt.ts PROMPT (lines 1-181).
# Fully static — cache-prefix-stable. Injected only when todo_write is enabled.
# Splice order: base prompt → ## Memory Management → ## Todo Management.
# ---------------------------------------------------------------------------

_TODO_MANAGEMENT_SECTION: str = """\
## Todo Management

Use this tool to create and manage a structured task list for your current \
coding session. This helps you track progress, organize complex tasks, and \
demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall \
progress of their requests.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps \
or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or \
multiple operations
3. User explicitly requests todo list - When the user directly asks you to \
use the todo list
4. User provides multiple tasks - When users provide a list of things to be \
done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements \
as todos
6. When you start working on a task - Mark it as in_progress BEFORE \
beginning work. Ideally you should only have one todo as in_progress at a time
7. After completing a task - Mark it as completed and add any new follow-up \
tasks discovered during implementation

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to \
do. In this case you are better off just doing the task directly.

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully

   **IMPORTANT**: Task descriptions must have two forms:
   - content: The imperative form describing what needs to be done \
(e.g., "Run tests", "Build the project")
   - activeForm: The present continuous form shown during execution \
(e.g., "Running tests", "Building the project")

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Exactly ONE task must be in_progress at any time (not less, not more)
   - Complete current tasks before starting new ones
   - Remove tasks that are no longer relevant from the list entirely

3. **Task Completion Requirements**:
   - ONLY mark a task as completed when you have FULLY accomplished it
   - If you encounter errors, blockers, or cannot finish, keep the task as \
in_progress
   - When blocked, create a new task describing what needs to be resolved
   - Never mark a task as completed if:
     - Tests are failing
     - Implementation is partial
     - You encountered unresolved errors
     - You couldn't find necessary files or dependencies

4. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names
   - Always provide both forms:
     - content: "Fix authentication bug"
     - activeForm: "Fixing authentication bug"

When in doubt, use this tool. Being proactive with task management \
demonstrates attentiveness and ensures you complete all requirements \
successfully.\
"""


# ---------------------------------------------------------------------------
_MEMORY_MANAGEMENT_SECTION: str = """\
## Memory Management

You have access to a persistent memory system. Use the `write_memory_entry`
tool to save important information across conversations.

**Four memory types:**
- `user` — information about the user (role, preferences, expertise)
- `feedback` — guidance the user has given you (what to do / avoid)
- `project` — ongoing work context, goals, decisions, deadlines
- `reference` — pointers to external resources, docs, tickets

**What to save:** non-obvious facts, user preferences explicitly stated,
recurring patterns you notice, decisions with lasting impact.

**What NOT to save:** code snippets (use the codebase), git history (use
`git log`), ephemeral task details, anything already in CLAUDE.md,
speculative ideas the user hasn't confirmed.

**How to save:** use `write_memory_entry(type, id, name, description, body)`.
The `id` is a kebab-case slug (optionally `type/slug` for organization).
The `description` is a ≤150-char summary used in the memory index.

The existing memory index is shown in the `## Memory` section below.\
"""


# ---------------------------------------------------------------------------
# ContextBudget
# ---------------------------------------------------------------------------

@dataclass
class ContextBudget:
    """Token budget for one queryLoop iteration.

    Source: effectiveContextWindow arithmetic in src/query.ts.
      available_tokens = max_tokens - reserved_output_tokens
    The autocompact trigger fires when used tokens exceed available_tokens.
    """
    max_tokens: int
    reserved_output_tokens: int

    @property
    def available_tokens(self) -> int:
        return self.max_tokens - self.reserved_output_tokens

    def is_over_budget(self, used_tokens: int) -> bool:
        return used_tokens > self.available_tokens

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Char/4 heuristic from roughTokenCountEstimationForMessages()."""
        return len(text) // 4


# ---------------------------------------------------------------------------
# BuiltContext
# ---------------------------------------------------------------------------

@dataclass
class BuiltContext:
    """The assembled context ready to send to the Anthropic API.

    system   -- fully assembled system prompt (base + memory + summary)
    messages -- post-compact, tool-result-processed, budget-trimmed API dicts
    """
    system: str
    messages: list[dict[str, Any]]
    estimated_tokens: int
    dropped_message_count: int
    externalized_tool_results: int
    budget: ContextBudget


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert a Message list to Anthropic API dicts, merging consecutive same-role.

    Mirrors normalizeMessagesForAPI() in src/utils/messages.ts:1989.
    Filters: is_virtual, COMPACT_BOUNDARY, SNIP_BOUNDARY, SYSTEM role.
    ATTACHMENT messages (M3 recent-file re-injection) are NOT filtered — they
    are user-role content the model must see and pass through unchanged.
    ATTACHMENT_MEMORY messages (M7 sideQuery injection) are also USER-role
    and pass through unchanged; _coalesce_same_role merges adjacent user
    messages so the <system-reminder> content lands before the user turn.
    M4: each TOOL_RESULT message's block content is wrapped in
    ``<msg uuid="...">...</msg>`` so the model can target it via the
    ``snip_history`` tool (OpenAI Chat Completions strips per-message
    metadata). ATTACHMENT/ATTACHMENT_MEMORY messages are NOT wrapped — the
    wrap gates on ``msg.type == TOOL_RESULT``.
    """
    result: list[dict[str, Any]] = []

    for msg in messages:
        if msg.is_virtual:
            continue
        if msg.type in (
            MessageType.COMPACT_BOUNDARY,
            MessageType.SNIP_BOUNDARY,
        ):
            continue
        if msg.role == Role.SYSTEM:
            continue

        api_content: str | list[dict[str, Any]]
        if isinstance(msg.content, str):
            api_content = msg.content
        else:
            blocks: list[dict[str, Any]] = []
            for item in msg.content:
                if isinstance(item, ToolCall):
                    blocks.append({
                        "type": "tool_use",
                        "id": item.id,
                        "name": item.name,
                        "input": item.input,
                    })
                elif isinstance(item, ToolResult):
                    block = item.to_api_block()
                    if msg.type == MessageType.TOOL_RESULT:
                        block = {
                            **block,
                            "content": f'<msg uuid="{msg.uuid}">{block["content"]}</msg>',
                        }
                    blocks.append(block)
            api_content = blocks

        api_msg: dict[str, Any] = {"role": msg.role.value, "content": api_content}

        if result and result[-1]["role"] == api_msg["role"]:
            prev = result[-1]
            prev["content"] = _merge_content(prev["content"], api_msg["content"])
        else:
            result.append(api_msg)

    return result


def _merge_content(
    prev: str | list[dict[str, Any]],
    nxt: str | list[dict[str, Any]],
) -> str | list[dict[str, Any]]:
    """Combine two API message contents of the same role into one.

    String pair -> newline-joined string; block-list pair -> concatenated
    blocks; mixed -> the string side is wrapped as a ``text`` block so the
    result is always a single coherent content value. Returns a NEW object;
    never mutates either input.
    """
    if isinstance(prev, str) and isinstance(nxt, str):
        return prev + "\n" + nxt
    if isinstance(prev, list) and isinstance(nxt, list):
        return prev + nxt
    if isinstance(prev, str) and isinstance(nxt, list):
        return [{"type": "text", "text": prev}] + nxt
    # prev is list, nxt is str
    assert isinstance(prev, list)
    return prev + [{"type": "text", "text": nxt}]


def _coalesce_same_role(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge consecutive same-role API dicts so the payload has no adjacent
    same-role turns (the Anthropic Messages API rejects them; OpenAI tolerates
    them).

    Applied once to the fully assembled payload because the post-trim prepend
    of recent-file attachments (M3) and the snip nudge (M4) can place several
    user-role dicts ahead of a user-role kept message, bypassing the merge in
    :func:`_normalize_messages`. Idempotent: a payload that already alternates
    roles passes through unchanged.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if result and result[-1]["role"] == msg["role"]:
            result[-1]["content"] = _merge_content(result[-1]["content"], msg["content"])
        else:
            result.append(msg)
    return result


def _estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(ContextBudget.estimate_tokens(json.dumps(m)) for m in messages)


def _attachment_dicts(
    compact_summary: CompactSummary | None,
) -> list[dict[str, Any]]:
    """Build one API dict per recent FileSnapshot on the compact summary (M3).

    Each snapshot becomes a separate ATTACHMENT user-role message; they are
    normalized individually so consecutive attachments are not merged into a
    single block (one snapshot == one ``<recent-files>`` message). Empty when
    there is no summary or no snapshots.
    """
    if compact_summary is None:
        return []
    dicts: list[dict[str, Any]] = []
    for snap in compact_summary.recent_file_snapshots:
        dicts.extend(_normalize_messages([Message.attachment(snap.path, snap.content)]))
    return dicts


def _snip_nudge_dict(nudge: SnipNudge) -> dict[str, Any]:
    """Render a SnipNudge as one user-role API message (M4).

    The nudge is an is_meta system-reminder telling the model it may call
    ``snip_history``; it is prepended ahead of the kept turns by
    ``ContextBuilder.build``.
    """
    return {"role": Role.USER.value, "content": nudge.render()}


def _todo_nudge_dict(nudge: TodoNudge) -> dict[str, Any]:
    """Render a TodoNudge as one user-role API message (plan-surface M1).

    Wraps render_todo_nudge_body() in <system-reminder> tags and returns a
    USER-role dict that _coalesce_same_role merges with adjacent user content.
    Source: messages.ts:3668-3678 wrapMessagesInSystemReminder path.
    """
    body = render_todo_nudge_body(nudge.todos)
    return {
        "role": Role.USER.value,
        "content": f"<system-reminder>\n{body}\n</system-reminder>",
    }


def _plan_mode_dict(attachment: PlanModeAttachment) -> dict[str, Any]:  # noqa: ARG001
    """Render a PlanModeAttachment as one user-role API message (plan-surface M2).

    Wraps ENTER_PLAN_MODE_TEACHING_TEXT in <system-reminder> tags and returns a
    USER-role dict. The PlanModeAttachment is an opaque marker; the actual text
    comes from the single source of truth in permission.py.
    Source: attachments.ts:1186 getPlanModeAttachments + messages.ts:3826
    case 'plan_mode' → wrapMessagesInSystemReminder.
    """
    return {
        "role": Role.USER.value,
        "content": (
            f"<system-reminder>\n{ENTER_PLAN_MODE_TEACHING_TEXT}\n</system-reminder>"
        ),
    }


def _remove_orphan_tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop tool_result blocks whose tool_use is no longer in context."""
    seen_tool_use_ids: set[str] = set()
    repaired: list[dict[str, Any]] = []

    for msg in messages:
        content = msg["content"]

        if msg["role"] == Role.ASSISTANT.value and isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use":
                    seen_tool_use_ids.add(str(block.get("id", "")))
            repaired.append(msg)
            continue

        if msg["role"] == Role.USER.value and isinstance(content, list):
            filtered: list[dict[str, Any]] = []
            for block in content:
                if block.get("type") != "tool_result":
                    filtered.append(block)
                    continue
                if str(block.get("tool_use_id", "")) in seen_tool_use_ids:
                    filtered.append(block)

            if filtered:
                repaired.append({**msg, "content": filtered})
            continue

        repaired.append(msg)

    return repaired


# ---------------------------------------------------------------------------
# ContextBuilder
# ---------------------------------------------------------------------------

class ContextBuilder:
    """Assembles the full context payload for one agent turn.

    Source: per-iteration pipeline in queryLoop() src/query.ts.

    Build order (mirrors source):
      1. Post-compact message slice
      2. Tool result externalization (oversized results -> disk pointers)
      3. Normalize to API format
      4. Budget check -> trim oldest messages until within budget
      5. System prompt assembly (base + memory snippets + compact summary)
    """

    def __init__(
        self,
        budget: ContextBudget,
        tool_result_store: ToolResultStore | None = None,
        workspace_path: Path | None = None,
        claude_md_loader: ClaudeMdLoader | None = None,
        project_memory: ProjectMemory | None = None,
        *,
        enable_todo_teaching: bool = False,
        tracer: Tracer | None = None,
    ) -> None:
        self._budget = budget
        self._store = tool_result_store or ToolResultStore()
        self._workspace_path = workspace_path
        self._claude_md_loader = claude_md_loader
        self._project_memory = project_memory
        self._enable_todo_teaching = enable_todo_teaching
        self._tracer: Tracer = tracer or NullTracer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        transcript: Transcript,
        system: str,
        compact_summary: CompactSummary | None = None,
        memory_snippets: list[str] | None = None,
        *,
        snip_nudge: SnipNudge | None = None,
        todo_nudge: TodoNudge | None = None,
        plan_mode_attachment: PlanModeAttachment | None = None,
    ) -> BuiltContext:
        """Assemble a BuiltContext from the current transcript state."""
        raw_messages = transcript.messages_after_compact_boundary()
        processed, externalized = self._process_tool_results(raw_messages)
        api_messages = _normalize_messages(processed)
        system_prompt = self._build_system_prompt(system, compact_summary, memory_snippets)

        system_tokens = ContextBudget.estimate_tokens(system_prompt)
        dropped = 0
        while api_messages and self._budget.is_over_budget(
            system_tokens + _estimate_messages_tokens(api_messages)
        ):
            api_messages.pop(0)
            dropped += 1
        api_messages = _remove_orphan_tool_results(api_messages)

        # M4: prepend the snip nudge (when armed) ahead of the kept turns.
        # plan-surface M1: prepend the todo nudge (when armed) ahead of kept turns.
        # plan-surface M2: prepend the plan-mode attachment (when armed) ahead of kept turns.
        # M3: re-attach recent-file snapshots in front of everything. The
        # final front-to-back order is [*attachments, snip_nudge, todo_nudge,
        # plan_mode_attachment, *kept] so the compact boundary → recent files →
        # snip → todo → plan mode → conversation ordering is preserved.
        # All are added AFTER trimming so none are ever popped to satisfy the budget.
        if plan_mode_attachment is not None:
            api_messages = [_plan_mode_dict(plan_mode_attachment)] + api_messages
        if todo_nudge is not None:
            api_messages = [_todo_nudge_dict(todo_nudge)] + api_messages
        if snip_nudge is not None:
            api_messages = [_snip_nudge_dict(snip_nudge)] + api_messages
        attachment_messages = _attachment_dicts(compact_summary)
        api_messages = attachment_messages + api_messages

        # The prepend above can place several user-role dicts (attachments,
        # nudge) ahead of a user-role kept message. Coalesce consecutive
        # same-role dicts so the payload is Anthropic-Messages-API compatible
        # (OpenAI tolerates adjacency; Anthropic rejects it). Order within the
        # merged content preserves [*attachments, nudge, *kept].
        api_messages = _coalesce_same_role(api_messages)

        estimated = system_tokens + _estimate_messages_tokens(api_messages)

        self._tracer.emit(
            "budget",
            available=self._budget.available_tokens,
            dropped=dropped,
            estimated_tokens=estimated,
            externalized=externalized,
            messages=len(api_messages),
            system_tokens=system_tokens,
        )
        return BuiltContext(
            system=system_prompt,
            messages=api_messages,
            estimated_tokens=estimated,
            dropped_message_count=dropped,
            externalized_tool_results=externalized,
            budget=self._budget,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_tool_results(
        self, messages: list[Message]
    ) -> tuple[list[Message], int]:
        """Replace oversized ToolResult content with store pointers.

        Collects all ToolResult items across all messages, calls
        process_results_batch() once (applies per-item threshold and 200k
        total budget), then rebuilds messages using an iterator over the
        batch output.  Creates new Message objects instead of mutating.

        Returns (processed_messages, externalized_count).
        """
        all_tr: list[tuple[str, str]] = [
            (item.tool_use_id, item.content)
            for msg in messages
            if isinstance(msg.content, list)
            for item in msg.content
            if isinstance(item, ToolResult)
        ]
        if not all_tr:
            return messages, 0

        batch_outputs = self._store.process_results_batch(all_tr)
        batch_iter = iter(batch_outputs)

        processed: list[Message] = []
        externalized = 0

        # Note: externalized counts all store hits, including cache re-serves on
        # repeated builds.  The field is informational; no code branches on it.
        for msg in messages:
            if not isinstance(msg.content, list):
                processed.append(msg)
                continue

            new_content: list[ToolCall | ToolResult] = []
            changed = False
            for item in msg.content:
                if isinstance(item, ToolResult):
                    out_content, stored = next(batch_iter)
                    if stored is not None:
                        externalized += 1
                        new_content.append(ToolResult(
                            tool_use_id=item.tool_use_id,
                            content=out_content,
                            is_error=item.is_error,
                            persisted_path=stored.path,
                            original_size=stored.original_size,
                        ))
                        changed = True
                    else:
                        new_content.append(item)
                else:
                    new_content.append(item)

            if changed:
                processed.append(Message(
                    uuid=msg.uuid,
                    role=msg.role,
                    content=new_content,
                    timestamp=msg.timestamp,
                    is_meta=msg.is_meta,
                    is_virtual=msg.is_virtual,
                    is_compact_summary=msg.is_compact_summary,
                    type=msg.type,
                ))
            else:
                processed.append(msg)

        return processed, externalized

    def _build_system_prompt(
        self,
        base: str,
        compact_summary: CompactSummary | None,
        memory_snippets: list[str] | None,
    ) -> str:
        """Combine base system prompt with memory and compact summary sections.

        Source: system prompt assembly in src/query.ts queryLoop().
        Returns base unchanged when no extras are provided.
        """
        if self._workspace_path is not None and self._claude_md_loader is not None:
            claude_md = self._claude_md_loader.load(self._workspace_path)
            if claude_md:
                base = f"{claude_md}\n\n---\n\n{base}"

        parts: list[str] = [base]

        if self._project_memory is not None:
            parts.append(_MEMORY_MANAGEMENT_SECTION)

        if self._enable_todo_teaching:
            parts.append(_TODO_MANAGEMENT_SECTION)

        if memory_snippets:
            parts.append("## Memory\n" + "\n".join(memory_snippets))

        if compact_summary is not None:
            parts.append("## Conversation Summary\n" + compact_summary.summary_text)

        if len(parts) == 1:
            return base

        return "\n\n".join(parts)
