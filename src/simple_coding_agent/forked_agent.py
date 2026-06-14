"""ForkedAgentRunner: generic isolated multi-turn sub-agent.

Source mapping:
  runForkedAgent        <- src/utils/forkedAgent.ts:489
    (promptMessages + canUseTool gate + maxTurns loop)
  createAutoMemCanUseTool <- src/services/extractMemories/extractMemories.ts:171
    (the canonical per-call allow/deny gate contract this runner accepts)
  createMemoryFileCanUseTool <- src/services/SessionMemory/sessionMemory.ts:460
    (a stricter sibling gate — M3 will build one this narrow)

Scope / explicitly NOT implemented (OpenAI-compatible target):
  - NO prompt-cache machinery (Anthropic CacheSafeParams /
    forkContextMessages cache-key preservation at forkedAgent.ts:478-486).
    OpenAI/DashScope caching is implicit/prefix-based — no fork-cache option
    exists.  LLM mode = a normal Provider.call loop; reusing the same prefix
    may get automatic cache benefit but we neither set nor depend on it.
  - NO OS-level sandbox / separate process.  Isolation = own message list +
    restricted can_use_tool gate + writes confined to a dir + bounded turns.
    (We do NOT replicate createSubagentContext abortController/appState/agentId
    plumbing at forkedAgent.ts:345-462.)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .models import ToolCall
from .provider import STOP_TOOL_USE, Provider
from .tools import ToolExecutor, ToolRegistry, UnknownToolError

__all__ = ["ForkedAgentResult", "ForkedAgentRunner"]


@dataclass(frozen=True)
class ForkedAgentResult:
    """Result of one ForkedAgentRunner.run() invocation."""

    errors: tuple[str, ...]
    turn_count: int


class ForkedAgentRunner:
    """Generic isolated multi-turn sub-agent.

    Runs at most ``max_turns`` provider calls.  On each turn:
      1. Calls the provider with the current messages.
      2. When the response requests tool use, checks ``can_use_tool`` for each
         tool call before dispatching:
         - DENIED  → appends is_error=True result with the gate's reason;
                     the tool NEVER reaches ToolExecutor / ToolRegistry.
         - ALLOWED → dispatches through ToolExecutor (UnknownToolError is
                     caught and returned as is_error=True).
      3. Continues until end_turn, or until ``max_turns`` is exhausted
         (for/else appends "max turns reached" to errors).

    ``context_messages`` are prepended to the message list on the first
    provider call so the sub-agent sees prior conversation context.

    Source: generalises ExtractMemoriesRunner (extract_memories.py) — that
    class is now a thin wrapper over this runner.
    """

    def __init__(
        self,
        provider: Provider,
        system_prompt: str,
        can_use_tool: Callable[[str, dict[str, Any]], tuple[bool, str]],
        tool_registry: ToolRegistry,
        max_turns: int = 10,
    ) -> None:
        self._provider = provider
        self._system_prompt = system_prompt
        self._can_use_tool = can_use_tool
        self._executor = ToolExecutor(tool_registry)
        self._tool_registry = tool_registry
        self._max_turns = max_turns

    def run(
        self,
        task_prompt: str,
        context_messages: list[dict[str, Any]] = (),  # type: ignore[assignment]
    ) -> ForkedAgentResult:
        """Run up to max_turns provider calls for the given task.

        Args:
            task_prompt:      The user-facing task instruction for the sub-agent.
            context_messages: Prior conversation messages to prepend (defensive
                              copy taken at call time; caller mutation is safe).
        """
        context_snapshot: list[dict[str, Any]] = list(context_messages)
        tools = self._tool_registry.to_api_format()

        # Build initial message list: prior context then the task prompt.
        messages: list[dict[str, Any]] = context_snapshot + [
            {"role": "user", "content": task_prompt}
        ]

        errors: list[str] = []
        turn_count = 0

        for _ in range(self._max_turns):
            response = self._provider.call(
                system=self._system_prompt,
                messages=messages,
                tools=tools,
            )
            turn_count += 1

            if response.stop_reason != STOP_TOOL_USE:
                break

            # Append assistant message with text + tool_use blocks.
            assistant_content: list[dict[str, Any]] = []
            if response.text:
                assistant_content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                })
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute each tool call; gate checked before ToolExecutor.
            tool_results: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                content, is_error = self._dispatch_tool(tc)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": content,
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            # for/else: all max_turns exhausted without a break (end_turn).
            errors.append("max turns reached")

        return ForkedAgentResult(
            errors=tuple(errors),
            turn_count=turn_count,
        )

    def _dispatch_tool(self, tc: ToolCall) -> tuple[str, bool]:
        """Check gate, then dispatch to executor.

        Gate deny returns (reason, True) without touching ToolExecutor — the
        same runtime-only soft-deny philosophy as loop.py::_execute_one (the
        plan-mode deny at lines 900-921).  The tools schema shown to the model
        is NOT filtered; the gate is purely a runtime allow/deny.
        """
        allow, reason = self._can_use_tool(tc.name, tc.input)
        if not allow:
            return reason, True
        try:
            return self._executor.execute(tc.name, tc.input)
        except UnknownToolError:
            return f"Tool '{tc.name}' is not currently registered", True
