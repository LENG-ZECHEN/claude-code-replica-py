"""
AgentLoop: minimal while-loop that orchestrates one user turn.

Source mapping:
  AgentLoop.run     <- queryLoop() in src/query.ts (while True { ... })
  LoopStatus        <- distilled from queryLoop()'s exit branches
                        (end_turn -> COMPLETED, max-iterations -> MAX_STEPS,
                         empty response -> MALFORMED)
  LoopResult        <- distilled summary of one queryLoop() invocation

Per-step pipeline (mirrors the spec in PYTHON_REPLICA_SPEC section 12):
  1. Compaction check (ContextCompactor.should_compact)
  2. Memory snippets (SessionMemory + ProjectMemory)
  3. Build context (ContextBuilder.build)
  4. Provider call (Provider.call)
  5. Branch on response:
       text-only         -> COMPLETED
       tool_calls        -> execute, append, loop
       neither           -> MALFORMED
  6. After max_steps tool turns with no final answer -> MAX_STEPS

The loop never raises on agent-runtime conditions (unknown tool, tool
exception, malformed response, exhausted max_steps).  All of those become
fields on the returned LoopResult so callers can react without try/except.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from .compact import ContextCompactor
from .context import ContextBudget, ContextBuilder
from .memory import ProjectMemory, SessionMemory
from .models import (
    AgentStep,
    CompactSummary,
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from .provider import STOP_MAX_TOKENS, PromptTooLongError, Provider
from .tool_result_store import ToolResultStore
from .tools import ToolExecutor, ToolRegistry, UnknownToolError
from .transcript import Transcript

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_MAX_STEPS: int = 10
_DEFAULT_SYSTEM_PROMPT: str = "You are a coding assistant."


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
    """Synchronous agent loop.

    Constructor wires together every component built in Phases 2-6:
      - Provider                  produces assistant responses
      - ToolExecutor              runs tool calls and captures errors
      - ToolRegistry (optional)   supplies the tool spec passed to the provider
      - Transcript                the running message history
      - ContextBuilder            assembles the per-turn API payload
      - ContextBudget             token budget shared with the compactor
      - ContextCompactor (opt)    summarizes old messages on threshold breach
      - SessionMemory (opt)       ephemeral memory injected into system prompt
      - ProjectMemory (opt)       file-backed memory injected into system prompt
      - ToolResultStore (opt)     externalizes oversized tool results to disk

    The loop keeps the most recent CompactSummary so it can re-inject the
    summary on subsequent turns even after the boundary marker has scrolled
    past.  The source persists this via the transcript itself, but our
    Transcript only stores the boundary marker, not the summary text.
    """

    def __init__(
        self,
        provider: Provider,
        tool_executor: ToolExecutor,
        transcript: Transcript,
        context_builder: ContextBuilder,
        budget: ContextBudget,
        registry: ToolRegistry | None = None,
        compactor: ContextCompactor | None = None,
        session_memory: SessionMemory | None = None,
        project_memory: ProjectMemory | None = None,
        tool_result_store: ToolResultStore | None = None,
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
        max_steps: int = _DEFAULT_MAX_STEPS,
    ) -> None:
        if max_steps < 1:
            raise ValueError(f"max_steps must be >= 1, got {max_steps}")
        self._provider = provider
        self._tool_executor = tool_executor
        self._transcript = transcript
        self._context_builder = context_builder
        self._budget = budget
        self._registry = registry
        self._compactor = compactor
        self._session_memory = session_memory
        self._project_memory = project_memory
        self._tool_result_store = tool_result_store
        self._system_prompt = system_prompt
        self._max_steps = max_steps
        self._last_summary: CompactSummary | None = None

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

        for turn in range(1, self._max_steps + 1):
            compacted_this_turn = self._maybe_compact()
            if compacted_this_turn:
                compacted_overall = True

            while True:
                memory_snippets = self._collect_memory_snippets()
                built = self._context_builder.build(
                    transcript=self._transcript,
                    system=self._system_prompt,
                    compact_summary=self._last_summary,
                    memory_snippets=memory_snippets,
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
                        return LoopResult(
                            answer=None,
                            steps=steps,
                            status=LoopStatus.MAX_TOKENS,
                            compacted=compacted_overall,
                            last_summary=self._last_summary,
                        )
                    reactive_compact_attempted = True
                    compacted_this_turn = self._force_compact()
                    compacted_overall = True

            # Branch 0: provider hit max_tokens; preserve any partial text but
            # do not report the turn as a clean completion.
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
                return LoopResult(
                    answer=response.text,
                    steps=steps,
                    status=LoopStatus.MAX_TOKENS,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                )

            # Branch 1: malformed (no text, no tool calls)
            if not response.text and not response.tool_calls:
                return LoopResult(
                    answer=None,
                    steps=steps,
                    status=LoopStatus.MALFORMED,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                )

            # Branch 2: tool calls -> execute and continue
            if response.tool_calls:
                if response.text:
                    self._transcript.append(Message.assistant(response.text))
                asst_msg, tool_results = self._handle_tool_calls(response.tool_calls)
                steps.append(AgentStep(
                    turn=turn,
                    user_message=initial_user_msg,
                    assistant_message=asst_msg,
                    tool_calls=list(response.tool_calls),
                    tool_results=tool_results,
                    compacted=compacted_this_turn,
                    memory_injected=list(memory_snippets),
                ))
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
            return LoopResult(
                answer=response.text,
                steps=steps,
                status=LoopStatus.COMPLETED,
                compacted=compacted_overall,
                last_summary=self._last_summary,
            )

        # Hit max_steps without a final answer.
        return LoopResult(
            answer=None,
            steps=steps,
            status=LoopStatus.MAX_STEPS,
            compacted=compacted_overall,
            last_summary=self._last_summary,
        )

    def run_stream(self, user_input: str) -> Iterator[LoopStreamEvent]:
        """Run the loop and yield assistant text as provider chunks arrive."""
        initial_user_msg = Message.user(user_input)
        self._transcript.append(initial_user_msg)

        steps: list[AgentStep] = []
        compacted_overall = False
        reactive_compact_attempted = False

        for turn in range(1, self._max_steps + 1):
            compacted_this_turn = self._maybe_compact()
            if compacted_this_turn:
                compacted_overall = True

            while True:
                memory_snippets = self._collect_memory_snippets()
                built = self._context_builder.build(
                    transcript=self._transcript,
                    system=self._system_prompt,
                    compact_summary=self._last_summary,
                    memory_snippets=memory_snippets,
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
                        )
                        yield LoopStreamEvent.done(result)
                        return
                    reactive_compact_attempted = True
                    compacted_this_turn = self._force_compact()
                    compacted_overall = True

            if response is None:
                result = LoopResult(
                    answer=None,
                    steps=steps,
                    status=LoopStatus.MALFORMED,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                )
                yield LoopStreamEvent.done(result)
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
                result = LoopResult(
                    answer=response.text,
                    steps=steps,
                    status=LoopStatus.MAX_TOKENS,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                )
                yield LoopStreamEvent.done(result)
                return

            if not response.text and not response.tool_calls:
                result = LoopResult(
                    answer=None,
                    steps=steps,
                    status=LoopStatus.MALFORMED,
                    compacted=compacted_overall,
                    last_summary=self._last_summary,
                )
                yield LoopStreamEvent.done(result)
                return

            if response.tool_calls:
                if response.text:
                    self._transcript.append(Message.assistant(response.text))
                asst_msg, tool_results = self._handle_tool_calls(response.tool_calls)
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
            result = LoopResult(
                answer=response.text,
                steps=steps,
                status=LoopStatus.COMPLETED,
                compacted=compacted_overall,
                last_summary=self._last_summary,
            )
            yield LoopStreamEvent.done(result)
            return

        result = LoopResult(
            answer=None,
            steps=steps,
            status=LoopStatus.MAX_STEPS,
            compacted=compacted_overall,
            last_summary=self._last_summary,
        )
        yield LoopStreamEvent.done(result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_compact(self) -> bool:
        """Run compaction if the compactor says we are over budget."""
        if self._compactor is None:
            return False
        if not self._compactor.should_compact(self._transcript, self._budget):
            return False
        self._force_compact()
        return True

    def _force_compact(self) -> bool:
        """Run compaction without checking the threshold."""
        if self._compactor is None:
            return False
        self._last_summary = self._compactor.compact(self._transcript, self._budget)
        return True

    def _collect_memory_snippets(self) -> list[str]:
        """Combine snippets from session and project memory stores."""
        snippets: list[str] = []
        if self._session_memory is not None:
            snippets.extend(self._session_memory.to_snippets())
        if self._project_memory is not None:
            snippets.extend(self._project_memory.to_snippets())
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

    def _execute_one(self, call: ToolCall) -> ToolResult:
        """Execute a single tool call; capture unknown-tool and runtime errors."""
        try:
            content, is_error = self._tool_executor.execute(call.name, call.input)
        except UnknownToolError:
            content = f"Unknown tool: {call.name}"
            is_error = True

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
