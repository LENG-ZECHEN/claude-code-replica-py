"""
Phase 10: Runnable CLI/demo for simple_coding_agent.

Drives the AgentLoop end-to-end against a deterministic MockProvider over a
temporary workspace. No LLM call is made; no API key is required; all file
operations are confined to the temporary directory and torn down on exit.

Entry point: ``simple-agent`` (declared in pyproject.toml ``[project.scripts]``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .context import ContextBudget, ContextBuilder
from .loop import AgentLoop, LoopStatus
from .models import ToolCall
from .provider import MockProvider, ProviderResponse
from .tool_registry_factory import build_default_registry
from .tools import ToolExecutor
from .transcript import Transcript

_USER_INPUT: str = (
    "Read src/app.py, find where 'hello' appears, "
    "and write a short REPORT.md summary."
)

_REPORT_BODY: str = (
    "# Demo report\n\n"
    "- Read src/app.py\n"
    "- Found 'hello' on the greet() return line\n"
    "- This file was written by simple-agent via MockProvider\n"
)

_FINAL_ANSWER: str = (
    "I read src/app.py, located the 'hello' substring on the greet() "
    "return line, and wrote a summary to REPORT.md."
)

_PREVIEW_CHARS: int = 200


def _seed_workspace(ws: Path) -> None:
    """Seed the temporary workspace with the file the script expects to read."""
    (ws / "src").mkdir()
    (ws / "src" / "app.py").write_text(
        "def greet(name):\n    return f'hello, {name}'\n",
        encoding="utf-8",
    )


def _script() -> list[ProviderResponse]:
    """Deterministic MockProvider script: read -> search -> write -> answer."""
    return [
        MockProvider.tool_call(
            "read_file", {"path": "src/app.py"}, id="tu_read"
        ),
        MockProvider.tool_call(
            "search_text", {"pattern": "hello"}, id="tu_search"
        ),
        MockProvider.tool_call(
            "write_file",
            {"path": "REPORT.md", "content": _REPORT_BODY},
            id="tu_write",
        ),
        MockProvider.direct_answer(_FINAL_ANSWER),
    ]


def _truncate(text: str, limit: int = _PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [+{len(text) - limit} more chars]"


def _format_call(call: ToolCall) -> str:
    kvs = ", ".join(f"{k}={_truncate(str(v), 60)!r}" for k, v in call.input.items())
    return f"{call.name}({kvs})"


def _run_demo(workspace: Path) -> int:
    """Wire components, run the loop, print a structured trace, return exit code."""
    _seed_workspace(workspace)
    registry = build_default_registry(workspace)
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    transcript = Transcript()
    builder = ContextBuilder(budget=budget)
    provider = MockProvider(_script())
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
    )

    print("=" * 60)
    print("simple_coding_agent -- MockProvider demo (Phase 10)")
    print("=" * 60)
    print(f"Workspace:   {workspace}")
    print(f"User input:  {_USER_INPUT}")
    print()

    result = loop.run(_USER_INPUT)

    for step in result.steps:
        print(f"--- Turn {step.turn} ---")
        if step.tool_calls:
            for call, res in zip(step.tool_calls, step.tool_results, strict=True):
                print(f"Tool call:   {_format_call(call)}")
                marker = "ERROR" if res.is_error else "Result"
                print(f"{marker}:      {_truncate(res.content)}")
        else:
            print(f"Final text:  {step.assistant_message.content}")
        print()

    print("--- Final answer ---")
    print(result.answer or "(no answer)")
    print()
    print(f"Loop status: {result.status}")
    report = workspace / "REPORT.md"
    print(f"Generated:   {report} (exists={report.exists()})")
    print()
    print(
        "Notes: MockProvider only -- no LLM call, no API key required. "
        "All file ops were confined to the temporary workspace."
    )
    print(
        "Gates: pytest, mypy, and ruff are expected to remain green after Phase 10."
    )

    return 0 if result.status == LoopStatus.COMPLETED else 1


def main() -> int:
    """Entry point for the ``simple-agent`` console script.

    Creates a throwaway workspace, drives the AgentLoop with a scripted
    MockProvider, and prints a structured trace. Returns a process exit code.
    """
    with tempfile.TemporaryDirectory(prefix="simple-agent-demo-") as tmp:
        return _run_demo(Path(tmp))


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
