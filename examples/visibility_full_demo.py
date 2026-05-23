"""P9 / M3: real-API visibility demo with persisted artifacts.

Run:

    OPENAI_API_KEY=... \\
    python examples/visibility_full_demo.py \\
        --confirm-api-call \\
        --model gpt-4o-mini

Safety-by-default:

  * Without ``--confirm-api-call``, the script prints an explanation
    and exits with code 2. ``OpenAIProvider`` is NOT constructed.
  * With ``--confirm-api-call`` but neither ``OPENAI_API_KEY`` nor
    ``DASHSCOPE_API_KEY`` set in env, the script prints an
    explanation and exits with code 3. ``OpenAIProvider`` is NOT
    constructed.

The happy path:

  1. Creates ``examples/_artifacts/visibility-demo-<UTC-timestamp>/``
     (override the parent dir via ``--output-root``).
  2. Opens ``trace.stderr`` and wires a ``StderrTracer`` whose stream
     points at that file, so every ``[trace] [<channel>]`` line is
     captured on disk.
  3. Builds an ``OpenAIProvider`` plus an ``AgentLoop`` via
     ``cli._build_repl_loop(..., aggressive_thresholds=True)`` so the
     context-management mechanisms (compact / microcompact / snip /
     externalize) actually fire on a short conversation.
  4. Drives three scripted user turns designed to exercise different
     channels (read a ~10KB file, read it again, leave a preference
     cue).
  5. Writes four artifacts to the run directory:

       - ``transcript.txt``  -- human-readable Transcript rendering
       - ``trace.stderr``    -- already written live by StderrTracer
       - ``metrics.json``    -- LoopResult.metrics serialised as JSON
       - ``summary.md``      -- one row per channel + tokens-per-turn

Artifact files are excluded from version control via the
``examples/_artifacts/`` entry in ``.gitignore`` -- do not commit
anything under that directory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from simple_coding_agent.cli import _AGGRESSIVE_THRESHOLDS, _build_repl_loop
from simple_coding_agent.coding_tools import ShellMode
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.provider import OpenAIProvider
from simple_coding_agent.trace import StderrTracer

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = _PROJECT_ROOT / "examples" / "_artifacts"
_SEED_FILE_NAME = "seed.txt"
_SEED_BODY_BYTES = 10_000

_TURN_INPUTS: tuple[str, ...] = (
    f"Please read {_SEED_FILE_NAME} so you know the contents.",
    f"Please read {_SEED_FILE_NAME} again to confirm what you saw.",
    "Please remember I prefer Python from now on.",
)

# Frozen channel vocabulary (HANDOFF Section 4 "do not modify").
_CHANNELS: tuple[str, ...] = (
    "budget",
    "compact",
    "reactive",
    "microcompact",
    "snip",
    "externalize",
    "memory_select",
    "claude_md",
    "auto_learn",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visibility_full_demo",
        description=(
            "End-to-end real-API demo of the observable-thresholds initiative. "
            "Refuses to call the API unless --confirm-api-call is passed."
        ),
    )
    parser.add_argument(
        "--confirm-api-call",
        action="store_true",
        help="Required to actually contact the API.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SIMPLE_AGENT_MODEL", "gpt-4o-mini"),
        help=(
            "Chat Completions model name. Defaults to "
            "$SIMPLE_AGENT_MODEL or 'gpt-4o-mini'."
        ),
    )
    parser.add_argument(
        "--output-root",
        default=str(_DEFAULT_ARTIFACT_ROOT),
        help=(
            "Parent directory for the per-run artifact folder. Defaults to "
            "examples/_artifacts/ inside the repository."
        ),
    )
    return parser


def _api_key_present() -> bool:
    return bool(
        os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    )


def _api_key_for_provider() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")


def _new_run_dir(root: Path) -> Path:
    """Create a fresh per-run artifact directory.

    Two demo runs that start in the same wall-clock second would otherwise
    share a timestamped directory and clobber each other's artifacts. When
    the base name is taken we append a ``-2`` … ``-9`` suffix; if all nine
    are occupied within one second we refuse rather than overwrite.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base = root / f"visibility-demo-{stamp}"
    if not base.exists():
        base.mkdir(parents=True)
        return base
    for suffix in range(2, 10):
        candidate = base.with_name(f"{base.name}-{suffix}")
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
    raise SystemExit(
        f"too many demo runs in the same second; clean {base.parent} "
        f"or wait a second"
    )


def _seed_workspace(workspace: Path) -> None:
    """Drop a ~10KB seed file the agent will be asked to read."""
    body = "lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 200
    (workspace / _SEED_FILE_NAME).write_text(
        body[:_SEED_BODY_BYTES], encoding="utf-8"
    )


def _format_call(call_input: dict[str, Any]) -> str:
    parts = []
    for key, value in call_input.items():
        text = str(value)
        if len(text) > 80:
            text = text[:80] + f"... [+{len(text) - 80}]"
        parts.append(f"{key}={text!r}")
    return ", ".join(parts)


def _render_transcript(payload: dict[str, Any]) -> str:
    """Render a JSON Transcript payload as human-readable text."""
    lines = ["# Transcript", ""]
    messages = payload.get("messages", [])
    for index, msg in enumerate(messages, start=1):
        role = msg.get("role", "?")
        msg_type = msg.get("type", "?")
        lines.append(f"## {index}. {role} ({msg_type})")
        content = msg.get("content", "")
        if isinstance(content, str):
            lines.append(content if content else "(empty)")
        elif isinstance(content, list):
            for block in content:
                block_type = block.get("type", "?")
                if block_type == "text":
                    lines.append(block.get("text", ""))
                elif block_type == "tool_use":
                    name = block.get("name", "?")
                    block_input = block.get("input", {})
                    lines.append(
                        f"tool_use {name}({_format_call(block_input)})"
                    )
                elif block_type == "tool_result":
                    body = block.get("content", "")
                    if isinstance(body, str) and len(body) > 200:
                        body = body[:200] + f"... [+{len(body) - 200}]"
                    lines.append(f"tool_result: {body}")
                else:
                    lines.append(f"{block_type}: {block!r}")
        else:
            lines.append(repr(content))
        lines.append("")
    return "\n".join(lines)


def _metrics_to_dict(metrics: MetricsCollector) -> dict[str, Any]:
    return {
        "full_compacts": metrics.full_compacts,
        "snip_invocations": metrics.snip_invocations,
        "microcompact_invocations": metrics.microcompact_invocations,
        "reactive_compacts": metrics.reactive_compacts,
        "externalized_bytes": metrics.externalized_bytes,
        "tokens_per_turn": list(metrics.tokens_per_turn),
    }


_QUOTES = ("'", '"')
_OPENERS = {"{": "}", "[": "]", "(": ")"}


def _scan_value(remainder: str, start: int) -> tuple[str, int]:
    """Read one field value beginning at ``start``; return (value, end).

    M1's ``trace._render_value`` repr-quotes whitespace-containing strings
    (``'a b'``) and structured types (``{'a': 1}`` / ``[1, 2]``), so a value
    can legally contain spaces. A bare ``split()`` would shred those across
    field boundaries. We therefore read quoted strings to their closing
    quote and bracketed reprs to their balanced close; everything else
    (scalars from before M1) reads up to the next whitespace as before.
    """
    n = len(remainder)
    first = remainder[start]
    if first in _QUOTES:
        i = start + 1
        while i < n:
            if remainder[i] == "\\":
                i += 2
                continue
            if remainder[i] == first:
                return remainder[start : i + 1], i + 1
            i += 1
        return remainder[start:n], n
    if first in _OPENERS:
        close, depth, quote, i = _OPENERS[first], 0, "", start
        while i < n:
            ch = remainder[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = ""
            elif ch in _QUOTES:
                quote = ch
            elif ch == first:
                depth += 1
            elif ch == close:
                depth -= 1
                if depth == 0:
                    return remainder[start : i + 1], i + 1
            i += 1
        return remainder[start:n], n
    i = start
    while i < n and not remainder[i].isspace():
        i += 1
    return remainder[start:i], i


def _parse_fields(remainder: str) -> dict[str, str]:
    """Parse a ``k1=v1 k2=v2 ...`` remainder, tolerating repr-quoted values."""
    fields: dict[str, str] = {}
    i, n = 0, len(remainder)
    while i < n:
        if remainder[i].isspace():
            i += 1
            continue
        key_start = i
        while i < n and remainder[i] != "=" and not remainder[i].isspace():
            i += 1
        if i >= n or remainder[i] != "=":
            # Fragment without '=' (e.g. a malformed token) — skip it.
            while i < n and not remainder[i].isspace():
                i += 1
            continue
        key = remainder[key_start:i]
        i += 1  # consume '='
        if i >= n or remainder[i].isspace():
            fields[key] = ""
            continue
        value, i = _scan_value(remainder, i)
        fields[key] = value
    return fields


def _parse_trace_events(stderr_path: Path) -> dict[str, list[dict[str, str]]]:
    """Group [trace] lines by channel.

    Locked format produced by ``StderrTracer.emit``:
        [trace] [<channel>] k1=v1 k2=v2 ...\\n
    Values may be repr-quoted (M1) — see ``_scan_value``.
    """
    events: dict[str, list[dict[str, str]]] = {}
    if not stderr_path.exists():
        return events
    raw = stderr_path.read_text(encoding="utf-8")
    prefix = "[trace] ["
    for line in raw.splitlines():
        if not line.startswith(prefix):
            continue
        rest = line[len(prefix):]
        channel, sep, remainder = rest.partition("]")
        if not sep:
            continue
        events.setdefault(channel.strip(), []).append(
            _parse_fields(remainder.lstrip())
        )
    return events


def _render_summary(
    metrics: MetricsCollector,
    events: dict[str, list[dict[str, str]]],
) -> str:
    """Render summary.md from metrics + parsed trace events."""
    lines = [
        "# Visibility demo summary",
        "",
        "## Channel counts",
        "",
        "| channel | trigger count | first fire site |",
        "| ------- | ------------- | --------------- |",
    ]
    for channel in _CHANNELS:
        channel_events = events.get(channel, [])
        count = len(channel_events)
        if channel_events:
            first = (
                ", ".join(
                    f"{k}={v}" for k, v in sorted(channel_events[0].items())
                )
                or "(no fields)"
            )
        else:
            first = "(never fired)"
        lines.append(f"| {channel} | {count} | {first} |")
    tokens_per_turn = (
        ", ".join(str(t) for t in metrics.tokens_per_turn) or "(no turns)"
    )
    lines.extend([
        "",
        "## Tokens per turn",
        "",
        tokens_per_turn,
        "",
        "## Counters",
        "",
        f"- full_compacts: {metrics.full_compacts}",
        f"- snip_invocations: {metrics.snip_invocations}",
        f"- microcompact_invocations: {metrics.microcompact_invocations}",
        f"- reactive_compacts: {metrics.reactive_compacts}",
        f"- externalized_bytes: {metrics.externalized_bytes}",
        "",
    ])
    return "\n".join(lines)


def _run(workspace: Path, run_dir: Path, model: str) -> None:
    """Drive the scripted conversation and write artifacts."""
    _seed_workspace(workspace)
    stderr_path = run_dir / "trace.stderr"
    with open(stderr_path, "w", encoding="utf-8") as stderr_fh:
        tracer = StderrTracer(stream=stderr_fh)
        provider = OpenAIProvider(
            model=model,
            api_key=_api_key_for_provider(),
            base_url=os.environ.get("OPENAI_BASE_URL"),
            max_tokens=int(_AGGRESSIVE_THRESHOLDS["reserved_output_tokens"]),
        )
        loop = _build_repl_loop(
            workspace,
            max_steps=4,
            max_context_tokens=int(_AGGRESSIVE_THRESHOLDS["context_tokens"]),
            reserved_output_tokens=int(
                _AGGRESSIVE_THRESHOLDS["reserved_output_tokens"]
            ),
            provider=provider,  # type: ignore[arg-type]
            shell_mode=ShellMode.MOCK,
            tracer=tracer,
            aggressive_thresholds=True,
        )
        for user_input in _TURN_INPUTS:
            loop.run(user_input)

    transcript_payload = loop._transcript.to_jsonable(include_virtual=True)
    (run_dir / "transcript.txt").write_text(
        _render_transcript(transcript_payload), encoding="utf-8"
    )
    (run_dir / "metrics.json").write_text(
        json.dumps(_metrics_to_dict(loop._metrics), indent=2) + "\n",
        encoding="utf-8",
    )
    events = _parse_trace_events(stderr_path)
    (run_dir / "summary.md").write_text(
        _render_summary(loop._metrics, events), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.confirm_api_call:
        print(
            "Refusing to call the API without --confirm-api-call. "
            "Re-run with --confirm-api-call once you intend to spend tokens."
        )
        return 2

    if not _api_key_present():
        print(
            "Set OPENAI_API_KEY or DASHSCOPE_API_KEY before running this demo.",
            file=sys.stderr,
        )
        return 3

    output_root = Path(args.output_root).expanduser().resolve()
    run_dir = _new_run_dir(output_root)
    with tempfile.TemporaryDirectory(prefix="visibility-demo-ws-") as raw:
        workspace = Path(raw)
        _run(workspace, run_dir, args.model)

    print(f"Wrote artifacts to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
