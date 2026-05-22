"""P9 / M2: demonstrate ``--aggressive-thresholds`` wiring (MockProvider).

Run:
    python examples/aggressive_thresholds_demo.py

Without this flag, the default context-management thresholds almost
never fire in a short conversation; demonstrating them requires
hand-crafting a 200KB stress fixture (see ``examples/stress_demo.py``).
The ``--aggressive-thresholds`` preset lowers every relevant threshold
in one switch so the same mechanisms become reachable in 8 short turns.

This demo wires a MockProvider-backed REPL with the preset applied via
``cli._build_repl_loop(..., aggressive_thresholds=True)`` and prints:

  * the one-line banner that the live REPL emits on stdout;
  * the constructor-time settings the preset injected into
    ``ContextCompactor``, ``MicroCompactor``, ``SnipTool``,
    ``ToolResultStore``, and ``ContextBudget``;
  * the per-mechanism counters after running 8 scripted turns with
    repeated ``read_file`` calls so snip has something to fold.

No network I/O, no API key, no real shell.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from simple_coding_agent.cli import (
    _AGGRESSIVE_THRESHOLDS,
    _build_repl_loop,
    _format_aggressive_banner,
)
from simple_coding_agent.coding_tools import ShellMode
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.trace import NullTracer, StderrTracer, Tracer

_NUM_TURNS = 8


def _build_scripted_provider() -> MockProvider:
    """Script alternates: read the same file, then a one-line answer."""
    script = []
    for turn in range(_NUM_TURNS):
        script.append(MockProvider.tool_call(
            "read_file",
            {"path": "src/app.py"},
            id=f"tu_read_{turn}",
        ))
        script.append(MockProvider.direct_answer(f"acknowledged turn {turn}"))
    return MockProvider(script)


def _seed_workspace(workspace: Path) -> None:
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "app.py").write_text(
        "def greet(name):\n    return f'hello, {name}'\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Demonstrate the --aggressive-thresholds preset by running a "
            "scripted 8-turn MockProvider conversation. Use --verbose to "
            "stream [trace] lines to stderr."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Stream [trace] event lines on stderr (StderrTracer).",
    )
    args = parser.parse_args(argv)
    tracer: Tracer = StderrTracer() if args.verbose else NullTracer()

    print(_format_aggressive_banner())
    print()
    print("Preset values applied at constructor time:")
    for key, value in _AGGRESSIVE_THRESHOLDS.items():
        print(f"  {key}: {value}")
    print()

    with tempfile.TemporaryDirectory(prefix="aggressive-demo-") as raw:
        workspace = Path(raw)
        _seed_workspace(workspace)

        loop = _build_repl_loop(
            workspace,
            max_steps=2,
            max_context_tokens=int(_AGGRESSIVE_THRESHOLDS["context_tokens"]),
            reserved_output_tokens=int(
                _AGGRESSIVE_THRESHOLDS["reserved_output_tokens"]
            ),
            provider=_build_scripted_provider(),
            shell_mode=ShellMode.MOCK,
            tracer=tracer,
            aggressive_thresholds=True,
        )

        for turn in range(_NUM_TURNS):
            loop.run(f"turn {turn}: please read src/app.py")

        print(loop._metrics.format_stats())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
