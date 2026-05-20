"""Run the simple coding agent with OpenAI Chat Completions.

Safety-by-default:
  - Does **not** call the API unless ``--confirm-api-call`` is passed.
  - ``--no-dotenv`` skips ``.env`` loading even if a ``.env`` file is present.
  - ``--dry-run`` prints what would be used and exits before constructing
    ``OpenAIProvider`` or contacting any network.
  - Secret-shaped env values (``OPENAI_API_KEY``, ``DASHSCOPE_API_KEY``)
    are reported as ``present`` / ``missing`` and are never printed.

Environment variables consulted (from the shell or a loaded ``.env``):
  SIMPLE_AGENT_MODEL          required Chat Completions model name
  OPENAI_API_KEY              preferred API key for the OpenAI SDK
  DASHSCOPE_API_KEY           fallback for DashScope OpenAI-compat endpoints
  OPENAI_BASE_URL             optional base URL override
  SIMPLE_AGENT_MAX_TOKENS     optional output cap per provider call
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopStatus
from simple_coding_agent.provider import OpenAIProvider
from simple_coding_agent.tool_registry_factory import build_default_registry
from simple_coding_agent.tools import ToolExecutor
from simple_coding_agent.transcript import Transcript

_USER_INPUT = (
    "Read src/app.py, find where 'hello' appears, "
    "and write a short REPORT.md summary."
)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DOTENV = _PROJECT_ROOT / ".env"
_DEFAULT_MAX_TOKENS = 1024


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


def _api_key_present() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY"))


def _api_key_for_provider() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")


def _max_tokens_from_env() -> int:
    raw = os.environ.get("SIMPLE_AGENT_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS))
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_TOKENS
    return max(value, 1)


def _seed_workspace(ws: Path) -> None:
    (ws / "src").mkdir()
    (ws / "src" / "app.py").write_text(
        "def greet(name):\n    return f'hello, {name}'\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openai_chat_demo",
        description=(
            "Optional OpenAI Chat Completions demo for simple_coding_agent. "
            "Refuses to call the API unless --confirm-api-call is passed."
        ),
    )
    parser.add_argument(
        "--no-dotenv",
        action="store_true",
        help=(
            "Do not read .env at all. Use this when you want the shell "
            "environment to be the only source of truth."
        ),
    )
    parser.add_argument(
        "--env-file",
        default=str(_DEFAULT_DOTENV),
        help=(
            "Path to a KEY=value env file. Defaults to python-replica/.env. "
            "Ignored when --no-dotenv is given."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the preflight summary (model, key presence, base URL, "
            "workspace, dotenv state) and exit before any network call."
        ),
    )
    parser.add_argument(
        "--confirm-api-call",
        action="store_true",
        help=(
            "Required to actually contact the API. Without this flag the "
            "demo prints a preflight summary and exits with code 3."
        ),
    )
    return parser


def _print_preflight(
    *,
    model: str | None,
    workspace: Path,
    dotenv_loaded_from: Path | None,
    no_dotenv: bool,
) -> None:
    """Print the preflight summary; never prints secret values."""
    base_url = os.environ.get("OPENAI_BASE_URL")
    print("--- Preflight ---")
    print(f"Model:              {model or '(missing — set SIMPLE_AGENT_MODEL)'}")
    print(f"OPENAI_API_KEY:     {'present' if os.environ.get('OPENAI_API_KEY') else 'missing'}")
    print(f"DASHSCOPE_API_KEY:  {'present' if os.environ.get('DASHSCOPE_API_KEY') else 'missing'}")
    print(f"OPENAI_BASE_URL:    {'set' if base_url else 'unset'}")
    print(f"Workspace:          {workspace}")
    if no_dotenv:
        print("Dotenv:             disabled (--no-dotenv)")
    elif dotenv_loaded_from is not None:
        print(f"Dotenv:             loaded from {dotenv_loaded_from}")
    else:
        print("Dotenv:             not found (no file loaded)")
    print(f"Max output tokens:  {_max_tokens_from_env()}")
    print("-----------------")


def _print_api_warning(model: str) -> None:
    print("WARNING: about to call a real OpenAI-compatible Chat Completions API.")
    print(f"         Model: {model}. This may incur cost on the configured endpoint.")
    print(f"         Endpoint: {os.environ.get('OPENAI_BASE_URL') or '(OpenAI default)'}")
    print()


def _run(workspace: Path, model: str) -> int:
    _seed_workspace(workspace)
    registry = build_default_registry(workspace)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    loop = AgentLoop(
        provider=OpenAIProvider(
            model=model,
            max_tokens=_max_tokens_from_env(),
            api_key=_api_key_for_provider(),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        ),
        tool_executor=ToolExecutor(registry),
        transcript=Transcript(),
        context_builder=ContextBuilder(budget=budget),
        budget=budget,
        registry=registry,
        system_prompt=(
            "You are a coding assistant. Use the provided tools when you need "
            "to inspect or write workspace files."
        ),
    )

    print(f"User input: {_USER_INPUT}")
    print()

    result = None
    streamed_text = False
    for event in loop.run_stream(_USER_INPUT):
        if event.type == "text_delta" and event.text:
            print(event.text, end="", flush=True)
            streamed_text = True
        elif event.type == "done" and event.result:
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


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    dotenv_loaded_from: Path | None = None
    if not args.no_dotenv:
        env_path = Path(str(args.env_file)).expanduser()
        if env_path.exists():
            _load_dotenv(env_path)
            dotenv_loaded_from = env_path

    model = os.environ.get("SIMPLE_AGENT_MODEL")

    with tempfile.TemporaryDirectory(prefix="simple-agent-openai-") as tmp:
        workspace = Path(tmp)

        _print_preflight(
            model=model,
            workspace=workspace,
            dotenv_loaded_from=dotenv_loaded_from,
            no_dotenv=bool(args.no_dotenv),
        )

        if args.dry_run:
            print("Dry-run: exiting before any network call.")
            return 0

        if not model:
            print(
                "Set SIMPLE_AGENT_MODEL to an OpenAI Chat Completions model "
                "(via the shell env or an .env file).",
                file=sys.stderr,
            )
            return 2

        if not _api_key_present():
            print(
                "Set OPENAI_API_KEY or DASHSCOPE_API_KEY before calling the API.",
                file=sys.stderr,
            )
            return 2

        if not args.confirm_api_call:
            print()
            print("Refusing to call the API without --confirm-api-call.")
            print(
                "Re-run with --confirm-api-call once you intend to spend tokens, "
                "or pass --dry-run to suppress this notice."
            )
            return 3

        _print_api_warning(model)
        return _run(workspace, model)


if __name__ == "__main__":
    raise SystemExit(main())
