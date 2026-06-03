"""Benchmark 1: Context compaction ratio at ~100K-token scale.

Goal: produce a hard, verifiable number for the resume bullet
"single-pass context compaction reduces token usage by N%".

Method:
  1. Seed a Transcript with ``_TOOL_EXCHANGE_COUNT`` (tool_use, tool_result)
     pairs whose tool_result bodies are each ``_TOOL_RESULT_CHARS`` long.
     Total chars target ~400K = ~100K estimated tokens (char/4 heuristic).
  2. Wire an ``AgentLoop`` to a small ``ContextBudget`` so the dual-trigger
     ``ContextCompactor.should_compact()`` fires on turn 1 with the
     ``RuleBasedSummarizer`` (deterministic, no API needed).
  3. Drive a single user turn; capture the resulting ``CompactSummary``
     plus the ``MetricsCollector`` snapshot.
  4. Emit results to ``benchmarks/_results/01_compression_ratio.{json,md}``.

No network I/O, no API key, deterministic.

Run:
    python -m benchmarks.bench_compression_ratio
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from simple_coding_agent.compact import ContextCompactor
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# Scale: 30 exchanges × 14_000 chars = 420_000 chars ≈ 105K estimated tokens.
_TOOL_EXCHANGE_COUNT = 30
_TOOL_RESULT_CHARS = 14_000

# Tiny budget forces ContextCompactor to fire on the first turn.
_BUDGET_MAX_TOKENS = 10_000
_BUDGET_RESERVED_OUTPUT = 2_000
_KEEP_RECENT = 4
_COMPACT_THRESHOLD = 0.5

_RESULTS_DIR = Path(__file__).resolve().parent / "_results"
_JSON_PATH = _RESULTS_DIR / "01_compression_ratio.json"
_MD_PATH = _RESULTS_DIR / "01_compression_ratio.md"


def _build_large_transcript() -> tuple[Transcript, int]:
    """Build a transcript with N (tool_use, tool_result) pairs."""
    transcript = Transcript()
    recent_ts = datetime.now(UTC).isoformat()
    total_chars = 0
    for i in range(_TOOL_EXCHANGE_COUNT):
        tool_use_id = f"tu_{i:03d}"
        transcript.append(Message(
            uuid=f"asst-{tool_use_id}",
            role=Role.ASSISTANT,
            content=[ToolCall(
                id=tool_use_id,
                name="read_file",
                input={"path": f"src/module_{i:03d}.py"},
            )],
            timestamp=recent_ts,
            type=MessageType.TOOL_USE,
        ))
        transcript.append(Message(
            uuid=f"user-{tool_use_id}",
            role=Role.USER,
            content=[ToolResult(
                tool_use_id=tool_use_id,
                content="x" * _TOOL_RESULT_CHARS,
            )],
            timestamp=recent_ts,
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        ))
        total_chars += _TOOL_RESULT_CHARS
        transcript.append(Message(
            uuid=f"asst-text-{i}",
            role=Role.ASSISTANT,
            content=f"observation about module_{i:03d}",
            timestamp=recent_ts,
        ))
    return transcript, total_chars


def _build_loop(transcript: Transcript) -> AgentLoop:
    budget = ContextBudget(
        max_tokens=_BUDGET_MAX_TOKENS,
        reserved_output_tokens=_BUDGET_RESERVED_OUTPUT,
    )
    compactor = ContextCompactor(
        keep_recent=_KEEP_RECENT,
        compact_threshold=_COMPACT_THRESHOLD,
    )
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    builder = ContextBuilder(budget=budget)
    provider = MockProvider([MockProvider.direct_answer(
        "Compaction benchmark answer."
    )])
    return AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        max_steps=3,
    )


def _run() -> dict[str, object]:
    transcript, total_chars = _build_large_transcript()
    loop = _build_loop(transcript)
    result = loop.run("summarize the entire investigation")

    summary = result.last_summary
    metrics = result.metrics

    pre_tokens = summary.pre_token_count if summary is not None else 0
    post_tokens = summary.post_token_count if summary is not None else 0
    summarized = summary.messages_summarized if summary is not None else 0
    ratio_pct = (
        round(100.0 * (pre_tokens - post_tokens) / pre_tokens, 2)
        if pre_tokens > 0
        else 0.0
    )

    return {
        "scenario": "Single-turn full compaction at ~100K-token scale",
        "config": {
            "tool_exchanges": _TOOL_EXCHANGE_COUNT,
            "tool_result_chars_each": _TOOL_RESULT_CHARS,
            "total_chars_seeded": total_chars,
            "estimated_tokens_seeded": total_chars // 4,
            "budget_max_tokens": _BUDGET_MAX_TOKENS,
            "budget_reserved_output_tokens": _BUDGET_RESERVED_OUTPUT,
            "compactor_keep_recent": _KEEP_RECENT,
            "compactor_threshold": _COMPACT_THRESHOLD,
        },
        "compaction": {
            "fired": result.compacted,
            "messages_summarized": summarized,
            "pre_tokens": pre_tokens,
            "post_tokens": post_tokens,
            "tokens_saved": pre_tokens - post_tokens,
            "compression_ratio_pct": ratio_pct,
        },
        "metrics": {
            "full_compacts": metrics.full_compacts if metrics else 0,
            "microcompact_invocations": (
                metrics.microcompact_invocations if metrics else 0
            ),
            "snip_invocations": metrics.snip_invocations if metrics else 0,
            "reactive_compacts": metrics.reactive_compacts if metrics else 0,
            "externalized_bytes": metrics.externalized_bytes if metrics else 0,
            "tokens_per_turn": (
                list(metrics.tokens_per_turn) if metrics else []
            ),
        },
        "loop_status": str(result.status),
    }


def _render_markdown(payload: dict[str, object]) -> str:
    cfg = payload["config"]
    cpx = payload["compaction"]
    mtr = payload["metrics"]
    lines = [
        "# Benchmark 1 — Compression Ratio at ~100K-token Scale",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Configuration",
        "",
        f"- Tool exchanges seeded: **{cfg['tool_exchanges']}** "
        f"(each tool_result = {cfg['tool_result_chars_each']:,} chars)",
        f"- Total seeded: **{cfg['total_chars_seeded']:,} chars** "
        f"≈ **{cfg['estimated_tokens_seeded']:,} estimated tokens**",
        f"- ContextBudget: max_tokens={cfg['budget_max_tokens']:,}, "
        f"reserved_output={cfg['budget_reserved_output_tokens']:,}",
        f"- ContextCompactor: keep_recent={cfg['compactor_keep_recent']}, "
        f"threshold={cfg['compactor_threshold']}",
        "",
        "## Result",
        "",
        f"- Compaction fired: **{cpx['fired']}**",
        f"- Messages summarized: **{cpx['messages_summarized']}**",
        f"- Pre-compact tokens:  **{cpx['pre_tokens']:,}**",
        f"- Post-compact tokens: **{cpx['post_tokens']:,}**",
        f"- Tokens saved:        **{cpx['tokens_saved']:,}**",
        f"- **Compression ratio: {cpx['compression_ratio_pct']}%**",
        "",
        "## MetricsCollector snapshot",
        "",
        f"- full_compacts: {mtr['full_compacts']}",
        f"- microcompact_invocations: {mtr['microcompact_invocations']}",
        f"- snip_invocations: {mtr['snip_invocations']}",
        f"- reactive_compacts: {mtr['reactive_compacts']}",
        f"- externalized_bytes: {mtr['externalized_bytes']:,}",
        f"- tokens_per_turn: {mtr['tokens_per_turn']}",
        "",
        f"- AgentLoop status: `{payload['loop_status']}`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = _run()
    _JSON_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _MD_PATH.write_text(_render_markdown(payload), encoding="utf-8")
    cpx = payload["compaction"]
    print(
        f"[bench1] pre={cpx['pre_tokens']:,} -> post={cpx['post_tokens']:,} "
        f"= {cpx['compression_ratio_pct']}% reduction "
        f"(summarized={cpx['messages_summarized']})"
    )
    print(f"[bench1] artifacts: {_JSON_PATH.name}, {_MD_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
