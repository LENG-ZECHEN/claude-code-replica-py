"""AgentLoop: while-loop that orchestrates one user turn (mirrors queryLoop() in query.ts)."""

from __future__ import annotations

import json
import uuid as _uuid
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from .coding_tools import (
    WRITE_MEMORY_ENTRY_SCHEMA,
    WRITE_MEMORY_ENTRY_TOOL_DESCRIPTION,
    WRITE_MEMORY_ENTRY_TOOL_NAME,
    write_memory_entry,
)
from .compact import ContextCompactor, MicroCompactor, SessionMemorySummarizer
from .context import ContextBudget, ContextBuilder
from .extraction_hooks import (
    maybe_extract_memories,
    maybe_update_session_memory,
)
from .memory import ProjectMemory, SessionMemory
from .metrics import MetricsCollector
from .models import (
    AgentStep,
    CompactSummary,
    FileSnapshot,
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from .permission import PermissionMode, PlanModeAttachment
from .plan_mode_tools import register_enter_plan_mode_tool, register_exit_plan_mode_tool
from .provider import STOP_MAX_TOKENS, PromptTooLongError, Provider
from .recall_hooks import inject_memory_attachments
from .session_memory_state import SessionMemoryState
from .snip import SnipTool
from .snip_tool_model import SnipNudge, snippable_candidate_uuids
from .todo import (
    TODO_REMINDER_TURNS,
    TodoItem,
    TodoNudge,
)
from .tool_result_store import ToolResultStore
from .tools import Tool, ToolExecutor, ToolRegistry, UnknownToolError
from .trace import NullTracer, Tracer
from .transcript import Transcript

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_MAX_STEPS: int = 10
_DEFAULT_SYSTEM_PROMPT: str = "You are a coding assistant."
_DEFAULT_RECENT_FILES_CAPACITY: int = 5
_DEFAULT_SNIP_NUDGE_GROWTH_TOKENS: int = 10_000


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_uuid() -> str:
    return str(_uuid.uuid4())


# ---------------------------------------------------------------------------
# LoopStatus
# ---------------------------------------------------------------------------

class LoopStatus(StrEnum):
    """How the loop exited."""
    COMPLETED = "completed"   # final text answer received
    MAX_STEPS = "max_steps"   # provider kept calling tools past max_steps
    MAX_TOKENS = "max_tokens" # provider stopped with a partial response
    MALFORMED = "malformed"   # provider returned no text and no tool calls


# ---------------------------------------------------------------------------
# LoopResult
# ---------------------------------------------------------------------------

@dataclass
class LoopResult:
    """Structured result of one AgentLoop.run() invocation."""
    answer: str | None
    steps: list[AgentStep]
    status: LoopStatus
    compacted: bool = False
    last_summary: CompactSummary | None = field(default=None, repr=False)
    metrics: MetricsCollector | None = field(default=None, repr=False)


@dataclass
class LoopStreamEvent:
    """Incremental event emitted by AgentLoop.run_stream()."""
    type: str
    text: str | None = None
    result: LoopResult | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    turn: int | None = None

    @staticmethod
    def text_delta(text: str, turn: int) -> LoopStreamEvent:
        return LoopStreamEvent(type="text_delta", text=text, turn=turn)

    @staticmethod
    def tool_step(
        call: ToolCall,
        result: ToolResult,
        turn: int,
    ) -> LoopStreamEvent:
        return LoopStreamEvent(type="tool_step", tool_call=call, tool_result=result, turn=turn)

    @staticmethod
    def done(result: LoopResult) -> LoopStreamEvent:
        return LoopStreamEvent(type="done", result=result)


# ---------------------------------------------------------------------------
# AgentLoop
# ---------------------------------------------------------------------------

class AgentLoop:
    """Synchronous agent loop (run) and streaming variant (run_stream)."""

    def __init__(
        self,
        provider: Provider,
        tool_executor: ToolExecutor,
        transcript: Transcript,
        context_builder: ContextBuilder,
        budget: ContextBudget,
        registry: ToolRegistry | None = None,
        compactor: ContextCompactor | None = None,
        microcompactor: MicroCompactor | None = None,
        snip_tool: SnipTool | None = None,
        session_memory: SessionMemory | None = None,
        project_memory: ProjectMemory | None = None,
        tool_result_store: ToolResultStore | None = None,
        metrics: MetricsCollector | None = None,
        tracer: Tracer | None = None,
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
        max_steps: int = _DEFAULT_MAX_STEPS,
        recent_files_capacity: int = _DEFAULT_RECENT_FILES_CAPACITY,
        snip_nudge_growth_tokens: int = _DEFAULT_SNIP_NUDGE_GROWTH_TOKENS,
        extract_memories_enabled: bool = False,
        extract_throttle_n: int = 1,
        session_memory_enabled: bool = False,
        is_subloop: bool = False,
        todo_nudge_enabled: bool = True,
        todo_reminder_turns: int = TODO_REMINDER_TURNS,
        todo_state: list[TodoItem] | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError(f"max_steps must be >= 1, got {max_steps}")
        if recent_files_capacity < 1:
            raise ValueError(
                f"recent_files_capacity must be >= 1, got {recent_files_capacity}"
            )
        if snip_nudge_growth_tokens < 1:
            raise ValueError(
                "snip_nudge_growth_tokens must be >= 1, got "
                f"{snip_nudge_growth_tokens}"
            )
        self._provider = provider
        self._tool_executor = tool_executor
        self._transcript = transcript
        self._context_builder = context_builder
        self._budget = budget
        self._registry = registry
        self._compactor = compactor
        self._tracer: Tracer = tracer or NullTracer()
        self._microcompactor = microcompactor or MicroCompactor()
        self._microcompacted_against_assistant_uuid: str | None = None
        self._snip_tool = snip_tool or SnipTool()
        self._snip_attempted_this_turn = False
        self._session_memory = session_memory
        self._project_memory = project_memory
        self._tool_result_store = tool_result_store
        self._metrics = metrics if metrics is not None else MetricsCollector()
        self._system_prompt = system_prompt
        self._max_steps = max_steps
        self._last_summary: CompactSummary | None = None
        self._recent_files_capacity = recent_files_capacity
        self._recent_file_snapshots: deque[FileSnapshot] = deque(
            maxlen=recent_files_capacity
        )
        self._snip_nudge_growth_tokens = snip_nudge_growth_tokens
        self._tokens_since_last_snip = 0
        self._snip_nudge_suppressed = False
        self._memory_writes_this_turn: int = 0
        self._is_subloop: bool = is_subloop
        self._extract_memories_enabled: bool = extract_memories_enabled
        self._memory_dir: Path | None = (
            Path(project_memory._dir)
            if project_memory is not None and hasattr(project_memory, "_dir")
            else None
        )
        self._auto_memory_enabled: bool = self._memory_dir is not None
        self._extraction_in_progress: bool = False
        self._last_memory_message_uuid: str | None = None
        self._turns_since_last_extraction: int = 0
        self._extract_throttle_n: int = max(1, extract_throttle_n)
        self._sm_enabled: bool = session_memory_enabled
        self._session_memory_state: SessionMemoryState = SessionMemoryState.empty()
        self._session_memory_cursor: str | None = None
        self._already_surfaced_memories: set[str] = set()
        self._session_bytes_used: int = 0
        self._todos: list[TodoItem] = todo_state if todo_state is not None else []
        self._todo_nudge_enabled = todo_nudge_enabled
        self._todo_reminder_turns = todo_reminder_turns
        self._todo_nudge_machinery_enabled = False  # computed after _register_tools
        self._turns_since_last_todo_write: int = 0
        self._turns_since_last_todo_reminder: int = 0
        self._permission_mode: PermissionMode = PermissionMode.NORMAL
        self._register_tools()
        self._todo_nudge_machinery_enabled = (
            todo_nudge_enabled
            and self._registry is not None
            and "todo_write" in self._registry._tools
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, user_input: str) -> LoopResult:
        """Run the loop until COMPLETED, MAX_STEPS, or MALFORMED."""
        initial_user_msg = Message.user(user_input)
        self._transcript.append(initial_user_msg)

        steps: list[AgentStep] = []
        compacted_overall = False
        reactive_compact_attempted = False
        self._snip_attempted_this_turn = False
        self._memory_writes_this_turn = 0
        self._session_bytes_used = inject_memory_attachments(
            self._transcript, user_input, self._provider, self._memory_dir,
            self._auto_memory_enabled, self._already_surfaced_memories,
            self._session_bytes_used, self._tracer)
        _todo_nudge = self._maybe_inject_todo_nudge()

        for turn in range(1, self._max_steps + 1):
            self._maybe_microcompact()
            self._maybe_snip()
            compacted_this_turn = self._maybe_compact()
            if compacted_this_turn:
                compacted_overall = True
            _plan_mode_attachment = self._maybe_arm_plan_mode_attachment()

            while True:
                memory_snippets = self._collect_memory_snippets(user_input)
                built = self._context_builder.build(
                    transcript=self._transcript,
                    system=self._system_prompt,
                    compact_summary=self._last_summary,
                    memory_snippets=memory_snippets,
                    snip_nudge=self._compute_snip_nudge(),
                    todo_nudge=_todo_nudge,
                    plan_mode_attachment=_plan_mode_attachment,
                )

                tools_spec = (
                    self._registry.to_api_format() if self._registry is not None else []
                )
                try:
                    response = self._provider.call(
                        system=built.system,
                        messages=built.messages,
                        tools=tools_spec,
                    )
                    break
                except PromptTooLongError:
                    if reactive_compact_attempted or self._compactor is None:
                        result = LoopResult(
                            answer=None,
                            steps=steps,
                            status=LoopStatus.MAX_TOKENS,
                            compacted=compacted_overall,
                            last_summary=self._last_summary,
                            metrics=self._metrics,
                        )
                        return self._run_stop_hooks(result)
                    reactive_compact_attempted = True
                    self._snip_nudge_suppressed = True
                    compacted_this_turn = self._force_compact()
                    self._tracer.emit("reactive", turn=turn)
                    self._metrics.record_reactive_compact()
                    compacted_overall = True

            # Clear the todo nudge after the FIRST successful build() so that
            # subsequent inner agent turns within this same user input don't
            # re-prepend the same nudge. Mirrors TS getTodoReminderTurnCounts
            # which fires per user turn, not per inner agent turn.
            _todo_nudge = None

            if response.stop_reason == STOP_MAX_TOKENS:
                if response.text:
                    partial_msg = Message.assistant(response.text)
                    self._transcript.append(partial_msg)
                    steps.append(AgentStep(
                        turn=turn,
                        user_message=initial_user_msg,
                        assistant_message=partial_msg,
                        tool_calls=[],
                        tool_results=[],
                        compacted=compacted_this_turn,
                        memory_injected=list(memory_snippets),
                    ))
                    self._metrics.record_turn_tokens(built.estimated_tokens)
                self._refresh_externalized_bytes()
                result = LoopResult(
                    answer=response.text,
                    steps=steps,
                    status=LoopStatus.MAX_TOKENS,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                    metrics=self._metrics,
                )
                return self._run_stop_hooks(result)

            # Branch 1: malformed (no text, no tool calls)
            if not response.text and not response.tool_calls:
                self._refresh_externalized_bytes()
                result = LoopResult(
                    answer=None,
                    steps=steps,
                    status=LoopStatus.MALFORMED,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                    metrics=self._metrics,
                )
                return self._run_stop_hooks(result)

            # Branch 2: tool calls -> execute and continue
            if response.tool_calls:
                if response.text:
                    self._transcript.append(Message.assistant(response.text))
                asst_msg, tool_results = self._handle_tool_calls(response.tool_calls)
                self._track_snip_nudge_growth(asst_msg, tool_results)
                steps.append(AgentStep(
                    turn=turn,
                    user_message=initial_user_msg,
                    assistant_message=asst_msg,
                    tool_calls=list(response.tool_calls),
                    tool_results=tool_results,
                    compacted=compacted_this_turn,
                    memory_injected=list(memory_snippets),
                ))
                self._metrics.record_turn_tokens(built.estimated_tokens)
                self._refresh_externalized_bytes()
                continue

            # Branch 3: final text answer
            final_msg = Message.assistant(response.text or "")
            self._transcript.append(final_msg)
            steps.append(AgentStep(
                turn=turn,
                user_message=initial_user_msg,
                assistant_message=final_msg,
                tool_calls=[],
                tool_results=[],
                compacted=compacted_this_turn,
                memory_injected=list(memory_snippets),
            ))
            self._metrics.record_turn_tokens(built.estimated_tokens)
            self._refresh_externalized_bytes()
            result = LoopResult(
                answer=response.text,
                steps=steps,
                status=LoopStatus.COMPLETED,
                compacted=compacted_overall,
                last_summary=self._last_summary,
                metrics=self._metrics,
            )
            return self._run_stop_hooks(result)

        # Hit max_steps without a final answer.
        self._refresh_externalized_bytes()
        result = LoopResult(
            answer=None,
            steps=steps,
            status=LoopStatus.MAX_STEPS,
            compacted=compacted_overall,
            last_summary=self._last_summary,
            metrics=self._metrics,
        )
        return self._run_stop_hooks(result)

    def run_stream(self, user_input: str) -> Iterator[LoopStreamEvent]:
        """Run the loop and yield assistant text as provider chunks arrive."""
        initial_user_msg = Message.user(user_input)
        self._transcript.append(initial_user_msg)

        steps: list[AgentStep] = []
        compacted_overall = False
        reactive_compact_attempted = False
        self._snip_attempted_this_turn = False
        self._memory_writes_this_turn = 0
        self._session_bytes_used = inject_memory_attachments(
            self._transcript, user_input, self._provider, self._memory_dir,
            self._auto_memory_enabled, self._already_surfaced_memories,
            self._session_bytes_used, self._tracer)
        _todo_nudge = self._maybe_inject_todo_nudge()

        for turn in range(1, self._max_steps + 1):
            self._maybe_microcompact()
            self._maybe_snip()
            compacted_this_turn = self._maybe_compact()
            if compacted_this_turn:
                compacted_overall = True
            _plan_mode_attachment = self._maybe_arm_plan_mode_attachment()

            while True:
                memory_snippets = self._collect_memory_snippets(user_input)
                built = self._context_builder.build(
                    transcript=self._transcript,
                    system=self._system_prompt,
                    compact_summary=self._last_summary,
                    memory_snippets=memory_snippets,
                    snip_nudge=self._compute_snip_nudge(),
                    todo_nudge=_todo_nudge,
                    plan_mode_attachment=_plan_mode_attachment,
                )
                tools_spec = (
                    self._registry.to_api_format() if self._registry is not None else []
                )

                response = None
                try:
                    for event in self._provider.stream_call(
                        system=built.system,
                        messages=built.messages,
                        tools=tools_spec,
                    ):
                        if event.type == "text_delta" and event.text:
                            yield LoopStreamEvent.text_delta(event.text, turn)
                        elif event.type == "done":
                            response = event.response
                    break
                except PromptTooLongError:
                    if reactive_compact_attempted or self._compactor is None:
                        result = LoopResult(
                            answer=None,
                            steps=steps,
                            status=LoopStatus.MAX_TOKENS,
                            compacted=compacted_overall,
                            last_summary=self._last_summary,
                            metrics=self._metrics,
                        )
                        yield LoopStreamEvent.done(self._run_stop_hooks(result))
                        return
                    reactive_compact_attempted = True
                    self._snip_nudge_suppressed = True
                    compacted_this_turn = self._force_compact()
                    self._tracer.emit("reactive", turn=turn)
                    self._metrics.record_reactive_compact()
                    compacted_overall = True

            # Clear the todo nudge after the FIRST successful build() so that
            # subsequent inner agent turns within this same user input don't
            # re-prepend the same nudge. Mirrors TS getTodoReminderTurnCounts
            # which fires per user turn, not per inner agent turn.
            _todo_nudge = None

            if response is None:
                self._refresh_externalized_bytes()
                result = LoopResult(
                    answer=None,
                    steps=steps,
                    status=LoopStatus.MALFORMED,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                    metrics=self._metrics,
                )
                yield LoopStreamEvent.done(self._run_stop_hooks(result))
                return

            if response.stop_reason == STOP_MAX_TOKENS:
                if response.text:
                    partial_msg = Message.assistant(response.text)
                    self._transcript.append(partial_msg)
                    steps.append(AgentStep(
                        turn=turn,
                        user_message=initial_user_msg,
                        assistant_message=partial_msg,
                        tool_calls=[],
                        tool_results=[],
                        compacted=compacted_this_turn,
                        memory_injected=list(memory_snippets),
                    ))
                    self._metrics.record_turn_tokens(built.estimated_tokens)
                self._refresh_externalized_bytes()
                result = LoopResult(
                    answer=response.text,
                    steps=steps,
                    status=LoopStatus.MAX_TOKENS,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                    metrics=self._metrics,
                )
                yield LoopStreamEvent.done(self._run_stop_hooks(result))
                return

            if not response.text and not response.tool_calls:
                self._refresh_externalized_bytes()
                result = LoopResult(
                    answer=None,
                    steps=steps,
                    status=LoopStatus.MALFORMED,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                    metrics=self._metrics,
                )
                yield LoopStreamEvent.done(self._run_stop_hooks(result))
                return

            if response.tool_calls:
                if response.text:
                    self._transcript.append(Message.assistant(response.text))
                asst_msg, tool_results = self._handle_tool_calls(response.tool_calls)
                self._track_snip_nudge_growth(asst_msg, tool_results)
                step = AgentStep(
                    turn=turn,
                    user_message=initial_user_msg,
                    assistant_message=asst_msg,
                    tool_calls=list(response.tool_calls),
                    tool_results=tool_results,
                    compacted=compacted_this_turn,
                    memory_injected=list(memory_snippets),
                )
                steps.append(step)
                self._metrics.record_turn_tokens(built.estimated_tokens)
                self._refresh_externalized_bytes()
                for call, tool_result in zip(step.tool_calls, step.tool_results, strict=True):
                    yield LoopStreamEvent.tool_step(call, tool_result, turn)
                continue

            final_msg = Message.assistant(response.text or "")
            self._transcript.append(final_msg)
            steps.append(AgentStep(
                turn=turn,
                user_message=initial_user_msg,
                assistant_message=final_msg,
                tool_calls=[],
                tool_results=[],
                compacted=compacted_this_turn,
                memory_injected=list(memory_snippets),
            ))
            self._metrics.record_turn_tokens(built.estimated_tokens)
            self._refresh_externalized_bytes()
            result = LoopResult(
                answer=response.text,
                steps=steps,
                status=LoopStatus.COMPLETED,
                compacted=compacted_overall,
                last_summary=self._last_summary,
                metrics=self._metrics,
            )
            yield LoopStreamEvent.done(self._run_stop_hooks(result))
            return

        self._refresh_externalized_bytes()
        result = LoopResult(
            answer=None,
            steps=steps,
            status=LoopStatus.MAX_STEPS,
            compacted=compacted_overall,
            last_summary=self._last_summary,
            metrics=self._metrics,
        )
        yield LoopStreamEvent.done(self._run_stop_hooks(result))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_stop_hooks(self, result: LoopResult) -> LoopResult:
        """Run post-turn hooks before returning from run() / run_stream()."""
        self._turns_since_last_extraction += 1
        if self._memory_dir is not None and self._registry is not None:
            was_in_progress = self._extraction_in_progress  # real flag, not literal False
            self._extraction_in_progress = True
            outcome = maybe_extract_memories(
                messages=self._transcript.all_messages(),
                base_messages_snapshot=self._transcript.normalize_for_api(),
                is_subloop=self._is_subloop,
                extract_memories_enabled=self._extract_memories_enabled,
                auto_memory_enabled=self._auto_memory_enabled,
                extraction_in_progress=was_in_progress,
                last_memory_message_uuid=self._last_memory_message_uuid,
                turns_since_last_extraction=self._turns_since_last_extraction,
                throttle_n=self._extract_throttle_n,
                provider=self._provider,
                memory_dir=self._memory_dir,
                system_prompt=self._system_prompt,
                tool_registry=self._registry,
                metrics=self._metrics,
            )
            self._extraction_in_progress = False
            self._last_memory_message_uuid = outcome.last_memory_message_uuid
            self._turns_since_last_extraction = outcome.turns_since_last_extraction
        sm_outcome = maybe_update_session_memory(
            messages=self._transcript.all_messages(),
            since_uuid=self._session_memory_cursor,
            state=self._session_memory_state,
            session_memory_enabled=self._sm_enabled,
            is_subloop=self._is_subloop,
        )
        if sm_outcome.ran:
            self._session_memory_state = sm_outcome.new_state
            self._session_memory_cursor = sm_outcome.new_cursor_uuid
        return result

    def _register_tools(self) -> None:
        """Wire write_memory_entry when project_memory is present, and todo_write when enabled."""
        if self._project_memory is not None and self._registry is not None:
            pm = self._project_memory

            def _write_memory_fn(
                type: str,
                id: str,
                name: str,
                description: str,
                body: str,
                tags: list[str] | None = None,
            ) -> str:
                if self._memory_writes_this_turn >= 3:
                    raise RuntimeError("memory write quota exhausted this turn (max 3)")
                self._memory_writes_this_turn += 1
                return write_memory_entry(pm, type, id, name, description, body, tags)

            self._registry.register(
                Tool(
                    name=WRITE_MEMORY_ENTRY_TOOL_NAME,
                    description=WRITE_MEMORY_ENTRY_TOOL_DESCRIPTION,
                    input_schema=WRITE_MEMORY_ENTRY_SCHEMA,
                    fn=_write_memory_fn,
                )
            )

        # Re-register enter_plan_mode and exit_plan_mode with this loop's real
        # mode setter and approval callback, overwriting the no-op lambdas placed
        # by build_default_registry. ToolRegistry.register() silently replaces.
        if self._registry is not None:
            register_enter_plan_mode_tool(self._registry, self._set_permission_mode)
            register_exit_plan_mode_tool(
                self._registry,
                self._set_permission_mode,
                self._exit_plan_mode_callback,
                metrics=self._metrics,
            )


    def _get_todos(self) -> list[TodoItem]:
        return list(self._todos)

    def _set_todos(self, todos: list[TodoItem]) -> None:
        self._todos = todos

    def _maybe_inject_todo_nudge(self) -> TodoNudge | None:
        """Return a TodoNudge when the double-AND counter fires, else None.

        Uses simple per-loop integer counters (not transcript scanning) so the
        N-th call to run() fires the nudge at exactly turn N regardless of
        how many messages are in the transcript at call time. The caller passes
        the returned value to ContextBuilder.build(todo_nudge=) so the nudge
        is injected fresh for that turn only and does not persist in transcript.

        Source: attachments.ts:3212-3317 getTodoReminderTurnCounts + arm logic.
        Double-AND: turns_since_write >= todo_reminder_turns AND
                    turns_since_reminder >= todo_reminder_turns.
        """
        if not self._todo_nudge_machinery_enabled:
            return None
        self._turns_since_last_todo_write += 1
        self._turns_since_last_todo_reminder += 1
        if (self._turns_since_last_todo_write >= self._todo_reminder_turns
                and self._turns_since_last_todo_reminder >= self._todo_reminder_turns):
            nudge = TodoNudge(todos=tuple(self._todos))
            self._tracer.emit(
                "todo",
                since_reminder=self._turns_since_last_todo_reminder,
                since_write=self._turns_since_last_todo_write,
            )
            self._metrics.record_todo_nudge_armed()
            self._turns_since_last_todo_reminder = 0
            return nudge
        return None

    def _maybe_compact(self) -> bool:
        """Run compaction if the compactor says we are over budget."""
        if self._compactor is None:
            return False
        if not self._compactor.should_compact(self._transcript, self._budget):
            return False
        self._force_compact()
        return True

    def _force_compact(self) -> bool:
        """Run compaction unconditionally.

        When --session-memory is on and the SM state is WARM, temporarily injects
        SessionMemorySummarizer so the summarization step returns prewarmed text
        with ZERO provider calls (O(0) compaction). Cold/disabled SM falls through
        to the configured Rule/LLM summarizer without crashing (null-vs-throw
        contract from autoCompact.ts:241 autoCompactIfNeeded :288/:312).
        """
        if self._compactor is None:
            return False
        snapshots = tuple(self._recent_file_snapshots)
        reused = self._sm_enabled and self._session_memory_state.is_warm
        if reused:
            orig_summarizer = self._compactor.summarizer
            self._compactor.summarizer = SessionMemorySummarizer(
                self._session_memory_state, fallback=orig_summarizer
            )
            try:
                self._last_summary = self._compactor.compact(
                    self._transcript, self._budget, snapshots=snapshots
                )
            finally:
                self._compactor.summarizer = orig_summarizer
        else:
            self._last_summary = self._compactor.compact(
                self._transcript, self._budget, snapshots=snapshots
            )
        self._tracer.emit("compact", reused=reused)
        self._metrics.record_full_compact()
        if reused:
            self._metrics.record_sm_compact_reuse()
        else:
            self._metrics.record_sm_compact_miss()
        self._tokens_since_last_snip = 0
        return True

    def _maybe_microcompact(self) -> bool:
        """Clear stale tool results; skip if already ran against this assistant msg."""
        messages = self._transcript.all_messages()
        latest_assistant_uuid = self._latest_assistant_uuid(messages)
        if (
            latest_assistant_uuid is not None
            and latest_assistant_uuid == self._microcompacted_against_assistant_uuid
        ):
            return False
        if not self._microcompactor.should_microcompact(messages):
            return False
        compacted = self._microcompactor.microcompact(messages)
        self._transcript.replace_all(compacted)
        self._microcompacted_against_assistant_uuid = latest_assistant_uuid
        self._metrics.record_microcompact()
        return True

    @staticmethod
    def _latest_assistant_uuid(messages: list[Message]) -> str | None:
        """Return the uuid of the most recent assistant message, or None."""
        for msg in reversed(messages):
            if msg.role == Role.ASSISTANT:
                return msg.uuid
        return None

    def _maybe_snip(self) -> bool:
        """Fold redundant tool results at most once per user turn."""
        if self._snip_attempted_this_turn:
            return False
        messages = self._transcript.all_messages()
        if not self._snip_tool.should_snip(messages):
            return False
        snipped = self._snip_tool.snip(messages)
        self._transcript.replace_all(snipped)
        self._snip_attempted_this_turn = True
        self._metrics.record_snip()
        # M4: an engine snip resets the snip-nudge growth window.
        self._tokens_since_last_snip = 0
        return True

    def _refresh_externalized_bytes(self) -> None:
        """Sample total externalized bytes from the store into metrics."""
        if self._tool_result_store is None:
            return
        self._metrics.externalized_bytes = (
            self._tool_result_store.total_externalized_bytes
        )

    def _collect_memory_snippets(self, query: str | None = None) -> list[str]:
        """Combine snippets from session and project memory stores."""
        snippets: list[str] = []
        if self._session_memory is not None:
            snippets.extend(self._session_memory.to_snippets())
        if self._project_memory is not None:
            snippets.extend(self._project_memory.to_snippets(query=query))
        return snippets

    def _handle_tool_calls(
        self, calls: list[ToolCall],
    ) -> tuple[Message, list[ToolResult]]:
        """Append the assistant tool_use message, execute tools, append results."""
        asst_msg = Message(
            uuid=_new_uuid(),
            role=Role.ASSISTANT,
            content=list(calls),
            timestamp=_now_iso(),
            type=MessageType.TOOL_USE,
        )
        self._transcript.append(asst_msg)

        tool_results = [self._execute_one(call) for call in calls]

        results_msg = Message(
            uuid=_new_uuid(),
            role=Role.USER,
            content=list(tool_results),
            timestamp=_now_iso(),
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        )
        self._transcript.append(results_msg)
        return asst_msg, tool_results

    def _track_snip_nudge_growth(
        self, asst_msg: Message, tool_results: list[ToolResult]
    ) -> None:
        """Reset the snip-nudge window on a successful model snip, else accumulate."""
        if self._snipped_via_tool(asst_msg, tool_results):
            self._tokens_since_last_snip = 0
            return
        self._tokens_since_last_snip += self._tool_turn_token_estimate(
            asst_msg, tool_results
        )

    @staticmethod
    def _snipped_via_tool(
        asst_msg: Message, tool_results: list[ToolResult]
    ) -> bool:
        """True iff this turn ran a ``snip_history`` call that did not error."""
        if not isinstance(asst_msg.content, list):
            return False
        for call, result in zip(asst_msg.content, tool_results, strict=False):
            if (
                isinstance(call, ToolCall)
                and call.name == "snip_history"
                and not result.is_error
            ):
                return True
        return False

    @staticmethod
    def _tool_turn_token_estimate(
        asst_msg: Message, tool_results: list[ToolResult]
    ) -> int:
        """Estimate the tokens a tool turn added (call inputs + result bodies)."""
        total = 0
        if isinstance(asst_msg.content, list):
            for call in asst_msg.content:
                if isinstance(call, ToolCall):
                    total += ContextBudget.estimate_tokens(json.dumps(call.input))
        for result in tool_results:
            total += ContextBudget.estimate_tokens(result.content)
        return total

    def _compute_snip_nudge(self) -> SnipNudge | None:
        """Return a SnipNudge when growth threshold is crossed and candidates exist."""
        if self._snip_nudge_suppressed:
            return None
        if self._tokens_since_last_snip < self._snip_nudge_growth_tokens:
            return None
        candidates = snippable_candidate_uuids(self._transcript.all_messages())
        if not candidates:
            return None
        return SnipNudge(candidate_uuids=tuple(candidates))

    def _exit_plan_mode_callback(self, plan: str) -> bool:
        """Default no-op approval callback used before cli.py wires the real one.

        Always returns False so that exit_plan_mode is inert in test setups that
        build the loop directly without _build_repl_loop. The real callback is
        _confirm_exit_plan from cli.py, injected via _register_tools.
        """
        return False

    def _set_permission_mode(self, mode: PermissionMode, *, source: str = "tool") -> None:
        """Flip permission mode; emit trace (with source) and record metrics.

        Idempotent: a transition to the current mode is a no-op (no metric
        bump, no trace emit). The TS EnterPlanModeTool documents itself as
        idempotent, and `enter_plan_mode` may be re-called inside PLAN
        without semantic effect — over-counting `plan_mode_entries` on
        re-entry would skew telemetry without telling us anything new.

        Exit-counter dispatch by source:
          - source == "slash"  → record_plan_mode_exit_manual()  (user /plan)
          - else               → record_plan_mode_exit_approved() (tool path
                                  reaches here only on the approved branch;
                                  rejection bumps `_rejected` from the
                                  exit_plan_mode factory before this runs)
        """
        if self._permission_mode == mode:
            return
        self._permission_mode = mode
        if mode == PermissionMode.PLAN:
            self._metrics.record_plan_mode_entry()
            self._tracer.emit("permission", mode="plan", source=source)
        else:
            if source == "slash":
                self._metrics.record_plan_mode_exit_manual()
            else:
                self._metrics.record_plan_mode_exit_approved()
            self._tracer.emit("permission", mode="normal", source=source)

    def _maybe_arm_plan_mode_attachment(self) -> PlanModeAttachment | None:
        """Return an opaque PlanModeAttachment marker when in PLAN mode, else None."""
        if self._permission_mode == PermissionMode.PLAN:
            return PlanModeAttachment()
        return None

    def _capture_file_snapshot(self, call: ToolCall, content: str) -> None:
        """Record a read_file result as a recent FileSnapshot (M3).

        Captures the live content returned by read_file BEFORE any
        externalization / microcompact / snip can alter the in-transcript
        tool_result. Newest-wins per path: a fresh read of an already-tracked
        path replaces its prior entry; the deque is capped at
        ``recent_files_capacity`` (oldest evicted).
        """
        path = call.input.get("path")
        if not isinstance(path, str):
            return
        kept = [s for s in self._recent_file_snapshots if s.path != path]
        kept.append(FileSnapshot(path=path, content=content, captured_at=_now_iso()))
        refreshed: deque[FileSnapshot] = deque(maxlen=self._recent_files_capacity)
        refreshed.extend(kept)
        self._recent_file_snapshots = refreshed

    def _execute_one(self, call: ToolCall) -> ToolResult:
        """Execute a single tool call; capture unknown-tool and runtime errors."""
        # Plan-mode soft-deny: block non-read-only tools before execution.
        # Unknown tools (not in registry) are treated as non-read-only and denied.
        if self._permission_mode == PermissionMode.PLAN and self._registry is not None:
            try:
                tool = self._registry.get(call.name)
                is_write = not tool.read_only
            except UnknownToolError:
                is_write = True
            if is_write:
                self._metrics.record_plan_mode_write_attempt()
                return ToolResult(
                    tool_use_id=call.id,
                    content=(
                        f"Plan mode active: '{call.name}' is not allowed. "
                        "Only read-only tools may be called in plan mode. "
                        "Use exit_plan_mode to submit your plan for approval, "
                        "or use /plan to exit plan mode manually."
                    ),
                    is_error=True,
                )

        try:
            content, is_error = self._tool_executor.execute(call.name, call.input)
        except UnknownToolError:
            content = f"Unknown tool: {call.name}"
            is_error = True

        if call.name == "read_file" and not is_error:
            self._capture_file_snapshot(call, content)

        if call.name == "todo_write" and not is_error:
            self._turns_since_last_todo_write = 0
            self._metrics.record_todo_write()

        if self._tool_result_store is None:
            return ToolResult(
                tool_use_id=call.id,
                content=content,
                is_error=is_error,
            )

        out_content, stored = self._tool_result_store.process_result(call.id, content)
        if stored is None:
            return ToolResult(
                tool_use_id=call.id,
                content=out_content,
                is_error=is_error,
            )
        return ToolResult(
            tool_use_id=call.id,
            content=out_content,
            is_error=is_error,
            persisted_path=stored.path,
            original_size=stored.original_size,
        )


__all__ = ["AgentLoop", "LoopResult", "LoopStatus", "LoopStreamEvent"]
