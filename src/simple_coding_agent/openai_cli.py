"""
Non-interactive OpenAI-compatible CLI for simple_coding_agent.

Run one task, print the final answer, then exit. This keeps the CLI aligned
with AgentLoop.run(user_input), which is currently a single-turn task runner.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .context import ContextBudget, ContextBuilder
from .loop import AgentLoop, LoopResult, LoopStatus
from .provider import OpenAIProvider
from .tool_registry_factory import build_default_registry
from .tools import ToolExecutor
from .transcript import Transcript

_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_CONTEXT_TOKENS = 200_000
_DEFAULT_RESERVED_OUTPUT_TOKENS = 8_192
_DEFAULT_SYSTEM_PROMPT = (
    "You are a coding assistant. Use the provided tools when you need "
    "to inspect or write workspace files."
)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load_dotenv(path: Path) -> None:
    """Load simple KEY=value lines without overriding existing shell env."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_quotes(value.strip())


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(int(raw), 1)
    except ValueError:
        return default


def _api_key_from_env() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")


def _resolve_workspace(raw: str) -> Path:
    workspace = Path(raw).expanduser().resolve()
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    return workspace


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simple-agent-openai",
        description="Run one simple_coding_agent task with OpenAI Chat Completions.",
    )
    parser.add_argument(
        "prompt",
        nargs="+",
        help="Task to run. Quote it to pass spaces as one argument.",
    )
    parser.add_argument(
        "-w",
        "--workspace",
        default=".",
        help="Workspace directory exposed to safe coding tools. Defaults to cwd.",
    )
    parser.add_argument(
        "-m",
        "--model",
        help="Chat Completions model. Defaults to SIMPLE_AGENT_MODEL.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        help="Provider max_tokens. Defaults to SIMPLE_AGENT_MAX_TOKENS or 1024.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to a KEY=value env file. Defaults to .env.",
    )
    parser.add_argument(
        "--no-dotenv",
        action="store_true",
        help="Do not load an env file before running.",
    )
    parser.add_argument(
        "--show-steps",
        action="store_true",
        help="Print tool calls and short tool results before the final answer.",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming and wait for each provider response before printing.",
    )
    return parser


def _format_result_preview(text: str, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [+{len(text) - limit} more chars]"


def _print_steps(result: LoopResult) -> None:
    for step in result.steps:
        if not step.tool_calls:
            continue
        print(f"--- Turn {step.turn} ---")
        for call, tool_result in zip(step.tool_calls, step.tool_results, strict=True):
            print(f"Tool: {call.name}({call.input})")
            marker = "ERROR" if tool_result.is_error else "Result"
            print(f"{marker}: {_format_result_preview(tool_result.content)}")
        print()


def _print_stream_tool_step(call_repr: str, result_repr: str, is_error: bool) -> None:
    print(file=sys.stderr)
    print(f"Tool: {call_repr}", file=sys.stderr)
    marker = "ERROR" if is_error else "Result"
    print(f"{marker}: {result_repr}", file=sys.stderr)
    print(file=sys.stderr)


def _run_task(
    *,
    prompt: str,
    workspace: Path,
    model: str,
    max_tokens: int,
    show_steps: bool,
    stream: bool,
) -> int:
    registry = build_default_registry(workspace)
    budget = ContextBudget(
        max_tokens=_DEFAULT_CONTEXT_TOKENS,
        reserved_output_tokens=_DEFAULT_RESERVED_OUTPUT_TOKENS,
    )
    loop = AgentLoop(
        provider=OpenAIProvider(
            model=model,
            max_tokens=max_tokens,
            api_key=_api_key_from_env(),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        ),
        tool_executor=ToolExecutor(registry),
        transcript=Transcript(),
        context_builder=ContextBuilder(budget=budget),
        budget=budget,
        registry=registry,
        system_prompt=_DEFAULT_SYSTEM_PROMPT,
    )

    print(f"Workspace: {workspace}")
    print(f"Model:     {model}")
    print(f"Task:      {prompt}")
    print()

    if stream:
        result: LoopResult | None = None
        streamed_text = False
        for event in loop.run_stream(prompt):
            if event.type == "text_delta" and event.text:
                print(event.text, end="", flush=True)
                streamed_text = True
                continue
            if event.type == "tool_step" and show_steps and event.tool_call and event.tool_result:
                _print_stream_tool_step(
                    f"{event.tool_call.name}({event.tool_call.input})",
                    _format_result_preview(event.tool_result.content),
                    event.tool_result.is_error,
                )
                continue
            if event.type == "done" and event.result:
                result = event.result

        if result is None:
            print("(no answer)")
            print(f"Status: {LoopStatus.MALFORMED}")
            return 1
        if streamed_text:
            print()
        else:
            print(result.answer or "(no answer)")
        print(f"Status: {result.status}")
        return 0 if result.status == LoopStatus.COMPLETED else 1

    result = loop.run(prompt)
    if show_steps:
        _print_steps(result)

    print(result.answer or "(no answer)")
    print(f"Status: {result.status}")
    return 0 if result.status == LoopStatus.COMPLETED else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.no_dotenv:
        _load_dotenv(Path(str(args.env_file)).expanduser())

    model = args.model or os.environ.get("SIMPLE_AGENT_MODEL")
    if not model:
        print("Set SIMPLE_AGENT_MODEL or pass --model.", file=sys.stderr)
        return 2

    if not _api_key_from_env():
        print("Set OPENAI_API_KEY or DASHSCOPE_API_KEY.", file=sys.stderr)
        return 2

    prompt = " ".join(str(part) for part in args.prompt).strip()
    if not prompt:
        print("Prompt must not be empty.", file=sys.stderr)
        return 2

    try:
        workspace = _resolve_workspace(str(args.workspace))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    max_tokens = args.max_tokens or _env_int("SIMPLE_AGENT_MAX_TOKENS", _DEFAULT_MAX_TOKENS)
    return _run_task(
        prompt=prompt,
        workspace=workspace,
        model=model,
        max_tokens=max_tokens,
        show_steps=bool(args.show_steps),
        stream=not bool(args.no_stream),
    )


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
