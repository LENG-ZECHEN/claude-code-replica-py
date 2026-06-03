"""
OpenAI-compatible CLI for simple_coding_agent.

Two modes:

  ``simple-agent-openai "<task>"``           one-shot Chat Completions run.
  ``simple-agent-openai --repl``             multi-turn REPL backed by the
                                             real provider; reuses every
                                             slash command (``/help``,
                                             ``/stats``, ``/save``,
                                             ``/load``, ``/remember``) and
                                             the auto-learn cue hook from
                                             the MockProvider REPL.

The REPL mode (P9-M5, A2) is what makes reactive compact reachable
against a real provider; with a tight ``--max-context-tokens`` the loop
will deterministically observe ``PromptTooLongError`` and retry.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import cli as _cli
from .coding_tools import ShellMode
from .context import ContextBudget, ContextBuilder
from .loop import AgentLoop, LoopResult, LoopStatus
from .memory import SessionMemory
from .provider import OpenAIProvider
from .tool_registry_factory import build_default_registry
from .tools import ToolExecutor
from .trace import NullTracer, StderrTracer, Tracer
from .transcript import Transcript

_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_CONTEXT_TOKENS = 200_000
_DEFAULT_RESERVED_OUTPUT_TOKENS = 8_192
_DEFAULT_SYSTEM_PROMPT = (
    "You are a coding assistant. Use the provided tools when you need "
    "to inspect or write workspace files."
)
_REPL_BANNER = (
    "simple-agent-openai REPL -- type /help for commands, /exit to quit.\n"
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
        description=(
            "Run a simple_coding_agent task with OpenAI Chat Completions. "
            "Use --repl for an interactive multi-turn session."
        ),
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="One-shot task. Omitted when --repl is set.",
    )
    parser.add_argument(
        "--repl",
        action="store_true",
        help="Start an interactive multi-turn REPL with the OpenAI provider.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Max tool-using iterations per user turn (REPL only; default: 10).",
    )
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        default=None,
        help=(
            "ContextBudget.max_tokens (REPL only; default: 200_000). If "
            "--aggressive-thresholds is also set and you do not pass this "
            "flag, the preset value applies; otherwise the built-in default "
            "applies."
        ),
    )
    parser.add_argument(
        "--snip-nudge-growth-tokens",
        type=int,
        default=None,
        help=(
            "AgentLoop.snip_nudge_growth_tokens (REPL only; default: 10_000): "
            "arm the model-driven snip_history nudge once context grows this "
            "many tokens since the last snip. Lower it (e.g. 500) WITH a roomy "
            "--max-context-tokens to exercise model snips without auto-compact "
            "preempting them. Not part of --aggressive-thresholds."
        ),
    )
    parser.add_argument(
        "--microcompact-minutes",
        type=int,
        default=None,
        metavar="N",
        help=(
            "MicroCompactor.threshold_minutes (REPL only; default: 60): "
            "clear compactable tool_results older than N minutes. 0 clears on "
            "the next turn. If --aggressive-thresholds is also set and you do "
            "not pass this flag, the preset value applies; otherwise the "
            "built-in default applies."
        ),
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        metavar="N",
        help=(
            "REPL only: exit cleanly after exactly N user turns, taking the "
            "same shutdown path as /exit. Slash commands do not count as turns. "
            "Useful for scripted artifact capture (M2 demo scenarios)."
        ),
    )
    parser.add_argument(
        "--reserved-output-tokens",
        type=int,
        default=None,
        help=(
            "ContextBudget.reserved_output_tokens (REPL only; default: 8_192). "
            "If --aggressive-thresholds is also set and you do not pass this "
            "flag, the preset value applies; otherwise the built-in default "
            "applies."
        ),
    )
    parser.add_argument(
        "--resume",
        default=None,
        metavar="NAME",
        help="Resume a previously saved REPL session by name (REPL only).",
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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Stream `[trace] [<channel>] k=v ...` lines to stderr for "
            "each compaction, snip, externalize, memory-select, and "
            "auto-learn cue (REPL mode)."
        ),
    )
    parser.add_argument(
        "--aggressive-thresholds",
        action="store_true",
        help=(
            "Lower every relevant context/memory threshold to demo-friendly "
            "values so compact / microcompact / snip / externalize actually "
            "fire in short REPL sessions. Explicit --max-context-tokens / "
            "--reserved-output-tokens / --max-steps still win per-field."
        ),
    )
    parser.add_argument(
        "--extract-memories",
        action="store_true",
        default=None,
        help=(
            "Enable automatic memory extraction after each turn (REPL mode). "
            "Also honoured via env SIMPLE_AGENT_EXTRACT_MEMORIES=1."
        ),
    )
    parser.add_argument(
        "--extract-throttle",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Run extraction at most once every N turns (default 1). "
            "Also honoured via env SIMPLE_AGENT_EXTRACT_THROTTLE."
        ),
    )
    parser.add_argument(
        "--shell-mode",
        choices=("mock", "allowlist"),
        default="mock",
        help=(
            "Shell tool execution mode. 'mock' (default) is safe and "
            "deterministic; 'allowlist' actually executes the 5-command "
            "allowlist (pwd, ls, cat, grep, python -m pytest)."
        ),
    )
    parser.add_argument(
        "--summarizer",
        choices=("auto", "rule", "llm"),
        default="auto",
        help=(
            "Compaction summarizer. 'auto' (default) reuses THIS "
            "OpenAIProvider instance (same model, same API key, same "
            "base_url) for LLM-based summarization. 'rule' forces "
            "RuleBasedSummarizer (no extra API call). 'llm' is identical "
            "to 'auto' here since openai-agent always has a real provider."
        ),
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
    shell_mode: ShellMode = ShellMode.MOCK,
) -> int:
    transcript = Transcript()
    registry = build_default_registry(
        workspace, shell_mode=shell_mode, transcript=transcript
    )
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
        transcript=transcript,
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


def _build_openai_repl_loop(
    workspace: Path,
    *,
    model: str,
    max_tokens: int,
    max_steps: int | None,
    max_context_tokens: int | None,
    reserved_output_tokens: int | None,
    snip_nudge_growth_tokens: int | None = None,
    microcompact_minutes: int | None = None,
    session_memory: SessionMemory,
    shell_mode: ShellMode = ShellMode.MOCK,
    tracer: Tracer | None = None,
    aggressive_thresholds: bool = False,
    extract_memories_enabled: bool = False,
    extract_throttle_n: int = 1,
    summarizer_mode: str = "auto",
) -> AgentLoop:
    """Wire a real-provider AgentLoop using the cli helper for everything else.

    The provider is the only difference from ``cli._build_repl_loop`` --
    we pass an ``OpenAIProvider`` instance instead of the MockProvider
    factory, plus a coder-oriented system prompt. ``summarizer_mode``
    propagates through to ``cli._build_repl_loop`` so the OpenAIProvider
    instance gets reused for LLM-based summarization in "auto" mode.
    """
    provider = OpenAIProvider(
        model=model,
        max_tokens=max_tokens,
        api_key=_api_key_from_env(),
        base_url=os.environ.get("OPENAI_BASE_URL"),
    )
    project_memory = _cli._open_project_memory(workspace, tracer=tracer)
    return _cli._build_repl_loop(
        workspace,
        max_steps=max_steps,
        max_context_tokens=max_context_tokens,
        reserved_output_tokens=reserved_output_tokens,
        snip_nudge_growth_tokens=snip_nudge_growth_tokens,
        microcompact_minutes=microcompact_minutes,
        session_memory=session_memory,
        project_memory=project_memory,
        provider=provider,
        system_prompt=_DEFAULT_SYSTEM_PROMPT,
        shell_mode=shell_mode,
        tracer=tracer,
        aggressive_thresholds=aggressive_thresholds,
        extract_memories_enabled=extract_memories_enabled,
        extract_throttle_n=extract_throttle_n,
        summarizer_mode=summarizer_mode,
    )


def _run_openai_repl(
    *,
    workspace: Path,
    model: str,
    max_tokens: int,
    max_steps: int | None,
    max_context_tokens: int | None,
    reserved_output_tokens: int | None,
    snip_nudge_growth_tokens: int | None = None,
    microcompact_minutes: int | None = None,
    max_turns: int | None = None,
    stream: bool,
    resume: str | None,
    shell_mode: ShellMode = ShellMode.MOCK,
    verbose: bool = False,
    aggressive_thresholds: bool = False,
    extract_memories_enabled: bool = False,
    extract_throttle_n: int = 1,
    show_steps: bool = False,
    summarizer_mode: str = "auto",
) -> int:
    """Drive the OpenAI-backed REPL, sharing slash commands with ``cli``.

    Reuses ``cli._drive_repl_session`` for the read/run/exit machinery so
    the REPL surface is identical between the MockProvider build
    (``simple-agent --repl``) and the live-provider build here.
    """
    print(_REPL_BANNER, end="")
    print(f"Workspace: {workspace}")
    print(f"Model:     {model}")
    if aggressive_thresholds:
        print(_cli._format_aggressive_banner())
    print()

    _cli._LAST_LOOPS.clear()
    session_mem_path = _cli._session_memory_path(workspace)
    session_memory = SessionMemory.load_json(session_mem_path)
    tracer: Tracer = StderrTracer() if verbose else NullTracer()
    loop = _build_openai_repl_loop(
        workspace,
        model=model,
        max_tokens=max_tokens,
        max_steps=max_steps,
        max_context_tokens=max_context_tokens,
        reserved_output_tokens=reserved_output_tokens,
        snip_nudge_growth_tokens=snip_nudge_growth_tokens,
        microcompact_minutes=microcompact_minutes,
        session_memory=session_memory,
        shell_mode=shell_mode,
        tracer=tracer,
        aggressive_thresholds=aggressive_thresholds,
        extract_memories_enabled=extract_memories_enabled,
        extract_throttle_n=extract_throttle_n,
        summarizer_mode=summarizer_mode,
    )

    if resume is not None:
        resume_rc = _cli._apply_resume(resume, loop)
        if resume_rc != 0:
            return resume_rc

    return _cli._drive_repl_session(
        loop,
        stream=stream,
        session_memory=session_memory,
        session_mem_path=session_mem_path,
        max_turns=max_turns,
        show_steps=show_steps,
    )


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

    repl_mode = bool(args.repl) or args.resume is not None
    prompt = " ".join(str(part) for part in args.prompt).strip()
    if not repl_mode and not prompt:
        print("Prompt must not be empty (or pass --repl).", file=sys.stderr)
        return 2

    try:
        workspace = _resolve_workspace(str(args.workspace))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    max_tokens = args.max_tokens or _env_int("SIMPLE_AGENT_MAX_TOKENS", _DEFAULT_MAX_TOKENS)
    shell_mode = ShellMode[str(args.shell_mode).upper()]

    if repl_mode:
        extract_enabled = bool(args.extract_memories) or bool(
            os.environ.get("SIMPLE_AGENT_EXTRACT_MEMORIES", "")
        )
        extract_throttle = args.extract_throttle or int(
            os.environ.get("SIMPLE_AGENT_EXTRACT_THROTTLE", "1")
        )
        return _run_openai_repl(
            workspace=workspace,
            model=model,
            max_tokens=max_tokens,
            max_steps=args.max_steps,
            max_context_tokens=args.max_context_tokens,
            reserved_output_tokens=args.reserved_output_tokens,
            snip_nudge_growth_tokens=args.snip_nudge_growth_tokens,
            microcompact_minutes=args.microcompact_minutes,
            max_turns=args.max_turns,
            stream=not bool(args.no_stream),
            resume=args.resume,
            shell_mode=shell_mode,
            verbose=bool(args.verbose),
            aggressive_thresholds=bool(args.aggressive_thresholds),
            extract_memories_enabled=extract_enabled,
            extract_throttle_n=extract_throttle,
            show_steps=bool(args.show_steps),
            summarizer_mode=str(args.summarizer),
        )

    return _run_task(
        prompt=prompt,
        workspace=workspace,
        model=model,
        max_tokens=max_tokens,
        show_steps=bool(args.show_steps),
        stream=not bool(args.no_stream),
        shell_mode=shell_mode,
    )


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
