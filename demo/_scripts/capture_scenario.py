"""M2 artifact capture driver — ctx-mgmt-demo.

Usage: python demo/_scripts/capture_scenario.py 01|02|03
Writes 4 artifacts per scenario to demo/_artifacts/<scenario>/
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simple_coding_agent.cli import _AGGRESSIVE_THRESHOLDS, _build_repl_loop
from simple_coding_agent.coding_tools import ShellMode
from simple_coding_agent.openai_cli import _api_key_from_env, _load_dotenv
from simple_coding_agent.provider import OpenAIProvider
from simple_coding_agent.trace import StderrTracer

_DEMO_DIR = Path(__file__).resolve().parents[1]      # python-replica/demo/
_ARTIFACTS_DIR = _DEMO_DIR / "_artifacts"
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

_SMALL = (
    "Context management design notes: context grows monotonically, "
    "tool results older than keep_recent are snipped, snipping preserves "
    "transcript shape while clearing superseded content. (< 300 chars)"
)
_LARGE = "context token data " * 200  # ~3800 chars > 2000-char inline limit
_SYS = (
    "You are a coding assistant. Use the provided tools when you need "
    "to inspect workspace files. Follow user instructions precisely."
)


@dataclass(frozen=True)
class ScenarioConfig:
    dir_name: str
    workspace_files: dict[str, str]
    turn_inputs: tuple[str, ...]
    microcompact_minutes: int | None = None


_SCENARIOS: dict[str, ScenarioConfig] = {
    "01": ScenarioConfig(
        dir_name="01_tool_result_management",
        workspace_files={"small.txt": _SMALL, "large.txt": _LARGE},
        turn_inputs=(
            "Please use the read_file tool to read small.txt and summarize it.",
            "Please use the read_file tool to read small.txt again to verify.",
            "Please use the read_file tool to read small.txt one more time and check for changes.",
            "Please use the read_file tool to read large.txt and give an overview.",
        ),
        # 3 reads of small.txt needed: should_snip() requires _PATH_THRESHOLD=3 reads
        # per path before firing. microcompact_minutes=60 prevents microcompact from
        # firing on slow API calls (qwen3.6-plus thinking mode ≈ 60s/call).
        microcompact_minutes=60,
    ),
    "02": ScenarioConfig(
        dir_name="02_full_compact",
        workspace_files={
            "notes1.txt": (
                "Alpha: context budget formula, keep_recent boundary, "
                "LLM summarizer fallback."
            ),
            "notes2.txt": (
                "Beta: microcompact cleanup, threshold_minutes, "
                "compactable tool list, idempotent."
            ),
            "notes3.txt": (
                "Gamma: snip tool folding, path-keyed dedup, "
                "snip_keep_recent, tool_use_id pairing."
            ),
        },
        turn_inputs=(
            "Please use the read_file tool to read notes1.txt and tell me what it says.",
            "Please use the read_file tool to read notes2.txt and describe its contents.",
            "Please use the read_file tool to read notes3.txt and explain the key points.",
            "Please summarize all three project files and highlight the main differences.",
        ),
    ),
    "03": ScenarioConfig(
        dir_name="03_microcompact",
        workspace_files={
            "notes.txt": (
                "Microcompact demo: data cleared when "
                "threshold_minutes=0 fires next turn."
            ),
        },
        turn_inputs=(
            "Please use the read_file tool to read notes.txt and tell me its contents.",
            "What do you remember from the notes.txt file you just read?",
        ),
        microcompact_minutes=0,
    ),
}


def _metrics_to_dict(metrics: Any) -> dict[str, Any]:
    return {
        "full_compacts": metrics.full_compacts,
        "snip_invocations": metrics.snip_invocations,
        "microcompact_invocations": metrics.microcompact_invocations,
        "reactive_compacts": metrics.reactive_compacts,
        "externalized_bytes": metrics.externalized_bytes,
        "tokens_per_turn": list(metrics.tokens_per_turn),
    }


def _render_transcript(payload: dict[str, Any]) -> str:
    lines = ["# Transcript", ""]
    for idx, msg in enumerate(payload.get("messages", []), start=1):
        lines.append(f"## {idx}. {msg.get('role','?')} ({msg.get('type','?')})")
        content = msg.get("content", "")
        if isinstance(content, str):
            lines.append(content or "(empty)")
        elif isinstance(content, list):
            for block in content:
                btype = block.get("type", "?")
                if btype == "text":
                    lines.append(block.get("text", ""))
                elif btype == "tool_use":
                    lines.append(f"tool_use {block.get('name','?')}({block.get('input',{})})")
                elif btype == "tool_result":
                    body = block.get("content", "")
                    if isinstance(body, str) and len(body) > 300:
                        body = body[:300] + f"... [+{len(body)-300}]"
                    lines.append(f"tool_result: {body}")
                else:
                    lines.append(repr(block)[:200])
        lines.append("")
    return "\n".join(lines)


def _run_scenario(
    config: ScenarioConfig, model: str, base_url: str | None, api_key: str
) -> None:
    artifact_dir = _ARTIFACTS_DIR / config.dir_name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stderr_path = artifact_dir / "trace.stderr"
    with (
        tempfile.TemporaryDirectory(prefix="demo-ws-") as raw,
        open(stderr_path, "w", encoding="utf-8") as stderr_fh,
    ):
        workspace = Path(raw)
        for name, body in config.workspace_files.items():
            (workspace / name).write_text(body, encoding="utf-8")
        tracer = StderrTracer(stream=stderr_fh)
        provider = OpenAIProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=int(_AGGRESSIVE_THRESHOLDS["reserved_output_tokens"]),
        )
        loop = _build_repl_loop(
            workspace,
            provider=provider,  # type: ignore[arg-type]
            shell_mode=ShellMode.MOCK,
            tracer=tracer,
            aggressive_thresholds=True,
            microcompact_minutes=config.microcompact_minutes,
            system_prompt=_SYS,
        )
        for turn_input in config.turn_inputs:
            loop.run(turn_input)

    (artifact_dir / "transcript.txt").write_text(
        _render_transcript(loop._transcript.to_jsonable(include_virtual=True)),
        encoding="utf-8",
    )
    # externalized_bytes is now wired through AgentLoop._refresh_externalized_bytes
    # (see [ctx-demo/review-fix] in cli.py); _metrics already carries the real value.
    metrics_dict = _metrics_to_dict(loop._metrics)
    (artifact_dir / "metrics.json").write_text(
        json.dumps(metrics_dict, indent=2) + "\n",
        encoding="utf-8",
    )
    stats_text = f"# model: {model}\n{loop._metrics.format_stats()}\n"
    (artifact_dir / "stats_output.txt").write_text(stats_text, encoding="utf-8")
    print(f"[capture] artifacts written to {artifact_dir}")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] not in _SCENARIOS:
        print(f"Usage: {Path(sys.argv[0]).name} 01|02|03", file=sys.stderr)
        return 2
    scenario_id = args[0]
    config = _SCENARIOS[scenario_id]
    _load_dotenv(_ENV_FILE)
    model = os.environ.get("SIMPLE_AGENT_MODEL")
    if not model:
        print("SIMPLE_AGENT_MODEL not set.", file=sys.stderr)
        return 2
    api_key = _api_key_from_env()
    if not api_key:
        print("Set DASHSCOPE_API_KEY or OPENAI_API_KEY.", file=sys.stderr)
        return 2
    base_url = os.environ.get("OPENAI_BASE_URL")
    print(f"[capture] scenario={scenario_id} ({config.dir_name}) model={model}")
    _run_scenario(config, model, base_url, api_key)
    m = json.loads((_ARTIFACTS_DIR / config.dir_name / "metrics.json").read_text())
    print(f"[capture] metrics: {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
