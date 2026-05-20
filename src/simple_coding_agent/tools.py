"""
Tool primitives: Tool, ToolRegistry, ToolExecutor, preview_result.

Source mapping:
  Tool / ToolRegistry  <- src/Tool.ts (BaseTool, tool registry)
  ToolExecutor         <- tool execution in src/query.ts queryLoop()
  preview_result       <- truncation logic in src/utils/toolResultStorage.ts
  max_result_chars     <- maxResultSizeChars = 50_000 in src/Tool.ts
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RESULT_CHARS: int = 50_000
PREVIEW_CHARS: int = 2_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def preview_result(content: str, limit: int = PREVIEW_CHARS) -> str:
    """Truncate content to limit chars, appending a count of omitted chars.

    Source: truncation logic in src/utils/toolResultStorage.ts.
    """
    if len(content) <= limit:
        return content
    remaining = len(content) - limit
    return content[:limit] + f"... [truncated, {remaining} more chars]"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UnknownToolError(KeyError):
    """Raised when a tool name is not registered."""


class ToolExecutionError(RuntimeError):
    """Raised when a tool's fn raises an unexpected error."""


# ---------------------------------------------------------------------------
# Tool dataclass
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """A single callable tool exposed to the model.

    Source: BaseTool in src/Tool.ts.
    max_result_chars mirrors maxResultSizeChars (default 50_000).
    Set to None to disable externalization for this tool.
    """
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., str]
    max_result_chars: int | None = MAX_RESULT_CHARS


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Maps tool names to Tool objects.

    Source: tool registration in src/query.ts / src/Tool.ts.
    Registering a name twice overwrites the previous entry.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError(name) from None

    def all_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_api_format(self) -> list[dict[str, Any]]:
        """Serialize registered tools to Anthropic API tool spec format."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]


# ---------------------------------------------------------------------------
# ToolExecutor
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Executes a named tool and returns (content, is_error).

    Source: tool dispatch in queryLoop() src/query.ts.
    Catches all exceptions from fn and returns them as is_error=True results
    so the model can see tool failures as tool_result blocks.
    UnknownToolError is NOT caught — it indicates a programming error.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, name: str, input: dict[str, Any]) -> tuple[str, bool]:
        """Run the named tool with input kwargs.

        Returns:
            (content, is_error) — content is always a string.
        Raises:
            UnknownToolError: if name is not registered.
        """
        tool = self._registry.get(name)
        try:
            result = tool.fn(**input)
            return str(result), False
        except Exception as exc:
            return str(exc), True
