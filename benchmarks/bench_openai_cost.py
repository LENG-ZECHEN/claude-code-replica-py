"""Benchmark 3: real-API token-cost comparison.

Goal: produce a hard, billable number for the resume bullet
"the full pipeline cuts prompt-token cost by N% on a 5-turn conversation".

Method
------
1. Seed an identical conversation transcript (8 tool exchanges, ~6 KB each
   ≈ 12K estimated tokens) into TWO independent ``AgentLoop`` instances:
   - **Full** loop: tiny ``ContextBudget``, ``ContextCompactor`` (with
     ``RuleBasedSummarizer`` — no extra API call), ``ToolResultStore``
     enabled (per-item 50 KB cap, total 200 KB cap), ``MicroCompactor``
     enabled.
   - **Naive** loop: 200K-token budget (effectively infinite for this
     scale), ``compactor=None``, ``tool_result_store=None`` (no
     externalization), ``microcompactor`` disabled via ``threshold_minutes``
     set high. The naive loop sees the full bloated transcript on every
     turn.
2. Drive **5 user turns** on each loop ("Summarize what we learned about
   module X"). Both loops talk to the same real model
   (gpt-4o-mini by default, or any DashScope/Qwen model via
   DASHSCOPE_API_KEY).
3. A ``UsageTrackingProvider`` decorator records every provider call's
   ``TokenUsage`` (input + output + cache_read + cache_creation tokens).
4. Compute total USD cost using the model price table at the bottom of
   this file. Default unit prices target Qwen-plus on DashScope; override
   with ``--input-price-per-1m`` / ``--output-price-per-1m``.
5. Emit ``benchmarks/_results/03_openai_cost.{json,md}``.

Safety
------
- Refuses to call the API without ``--confirm-api-call`` (exit code 2).
- Refuses without ``OPENAI_API_KEY`` or ``DASHSCOPE_API_KEY`` (exit code 3).
- Hard-caps total turns × loops at 10 (5 turns × 2 loops) so the worst
  case is bounded by the model's per-call budget.

Run examples
------------
    # Qwen on DashScope (cheap; auto-detects base_url)
    DASHSCOPE_API_KEY=sk-... \\
        python -m benchmarks.bench_openai_cost \\
            --confirm-api-call --model qwen-plus

    # gpt-4o-mini on OpenAI
    OPENAI_API_KEY=sk-... \\
        python -m benchmarks.bench_openai_cost \\
            --confirm-api-call --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from simple_coding_agent.compact import (
    ContextCompactor,
    LLMSummarizer,
    MicroCompactor,
    RuleBasedSummarizer,
    Summarizer,
)
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.provider import (
    OpenAIProvider,
    ProviderResponse,
    ProviderStreamEvent,
    TokenUsage,
)
from simple_coding_agent.tool_result_store import ToolResultStore
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Scale knobs (kept small to bound real-API spend)
# ---------------------------------------------------------------------------
_TOOL_EXCHANGE_COUNT = 8
_TOOL_RESULT_CHARS = 6_000   # ~1.5K tokens each
_TURNS = 5
_USER_QUESTIONS = [
    "Briefly summarize what you learned about module_000 from the prior reads.",
    "Now do the same for module_001 — keep it under 50 words.",
    "Compare module_002 and module_003 in one sentence each.",
    "List the names of all modules you have seen so far.",
    "Give a one-sentence conclusion about the whole codebase.",
]

# Full-pipeline budget — small enough to force compaction within 5 turns.
_FULL_BUDGET_TOKENS = 8_000
_FULL_RESERVED_OUTPUT = 1_500
_FULL_KEEP_RECENT = 4
_FULL_COMPACT_THRESHOLD = 0.5

# Naive budget — huge enough that nothing trims for the whole 5-turn run.
_NAIVE_BUDGET_TOKENS = 200_000
_NAIVE_RESERVED_OUTPUT = 4_096

# Resolved at runtime via the price table below.
_DEFAULT_MODEL = "qwen-plus"
_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

_RESULTS_DIR = Path(__file__).resolve().parent / "_results"


def _result_paths(summarizer_mode: str) -> tuple[Path, Path]:
    """Per-mode artifact paths so rule + llm runs don't overwrite each other."""
    suffix = "_llm" if summarizer_mode == "llm" else "_rule"
    return (
        _RESULTS_DIR / f"03_openai_cost{suffix}.json",
        _RESULTS_DIR / f"03_openai_cost{suffix}.md",
    )


# ---------------------------------------------------------------------------
# Model price table — USD per 1M tokens. Keep conservative; users override.
# ---------------------------------------------------------------------------
_MODEL_PRICES: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # DashScope Qwen (公开价 ¥/1K → USD/1M, exchange rate ≈ 7.15)
    "qwen-turbo": (0.08, 0.25),
    "qwen-turbo-latest": (0.08, 0.25),
    "qwen-plus": (0.11, 0.28),
    "qwen-plus-latest": (0.11, 0.28),
    "qwen-long": (0.07, 0.28),
    "qwen-long-latest": (0.07, 0.28),
    "qwen-max": (0.28, 0.84),
}


# ---------------------------------------------------------------------------
# UsageTrackingProvider — wraps any Provider, accumulates token usage.
# ---------------------------------------------------------------------------
@dataclass
class _UsageRecord:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    per_call: list[dict[str, int]] = field(default_factory=list)

    def add(self, usage: TokenUsage) -> None:
        self.calls += 1
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_input_tokens += usage.cache_read_input_tokens
        self.cache_creation_input_tokens += usage.cache_creation_input_tokens
        self.per_call.append({
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "cache_read": usage.cache_read_input_tokens,
            "cache_create": usage.cache_creation_input_tokens,
        })


class _UsageTrackingProvider:
    """Decorator that records TokenUsage across every provider call."""

    def __init__(self, inner: OpenAIProvider) -> None:
        self._inner = inner
        self.usage = _UsageRecord()

    def call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        response = self._inner.call(system=system, messages=messages, tools=tools)
        self.usage.add(response.usage)
        return response

    def stream_call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Iterator[ProviderStreamEvent]:
        for event in self._inner.stream_call(
            system=system, messages=messages, tools=tools,
        ):
            if event.type == "done" and event.response is not None:
                self.usage.add(event.response.usage)
            yield event

    def call_selector(
        self,
        *,
        system: str,
        user: str,
        output_schema: dict[str, Any],
        max_tokens: int = 256,
    ) -> dict[str, Any]:
        return self._inner.call_selector(
            system=system, user=user,
            output_schema=output_schema, max_tokens=max_tokens,
        )


# ---------------------------------------------------------------------------
# Transcript seeding
# ---------------------------------------------------------------------------
def _seeded_transcript() -> Transcript:
    """N (tool_use, tool_result) pairs + one observation each.

    Both loops start from an identical Transcript built by this function
    so the only variable in the experiment is the pipeline config.
    """
    transcript = Transcript()
    recent_ts = datetime.now(UTC).isoformat()
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
        body = (
            f"# module_{i:03d}.py — synthetic file body for cost benchmark\n"
            + ("def function_x(): pass\n" * 250)
        )[:_TOOL_RESULT_CHARS]
        transcript.append(Message(
            uuid=f"user-{tool_use_id}",
            role=Role.USER,
            content=[ToolResult(
                tool_use_id=tool_use_id,
                content=body,
            )],
            timestamp=recent_ts,
            type=MessageType.TOOL_RESULT,
            is_meta=True,
        ))
        transcript.append(Message(
            uuid=f"asst-text-{i}",
            role=Role.ASSISTANT,
            content=f"Acknowledged module_{i:03d}.",
            timestamp=recent_ts,
        ))
    return transcript


# ---------------------------------------------------------------------------
# Loop builders
# ---------------------------------------------------------------------------
def _build_full_loop(
    provider: _UsageTrackingProvider,
    transcript: Transcript,
    *,
    summarizer_mode: str = "rule",
) -> AgentLoop:
    """Tiny budget + compactor + tool result store + microcompact.

    ``summarizer_mode``:
      * "rule" — RuleBasedSummarizer (deterministic, zero extra API cost)
      * "llm"  — LLMSummarizer wrapping the same usage-tracked provider so
                 the summarization API call is billed into the run total.
    """
    budget = ContextBudget(
        max_tokens=_FULL_BUDGET_TOKENS,
        reserved_output_tokens=_FULL_RESERVED_OUTPUT,
    )
    summarizer: Summarizer
    if summarizer_mode == "llm":
        # Wrap the same UsageTrackingProvider so summary token spend
        # accumulates into the same _UsageRecord — the "real" cost.
        summarizer = LLMSummarizer(provider)  # type: ignore[arg-type]
    else:
        summarizer = RuleBasedSummarizer()
    compactor = ContextCompactor(
        keep_recent=_FULL_KEEP_RECENT,
        compact_threshold=_FULL_COMPACT_THRESHOLD,
        summarizer=summarizer,
    )
    tool_result_store = ToolResultStore()
    builder = ContextBuilder(budget=budget, tool_result_store=tool_result_store)
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    return AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        microcompactor=MicroCompactor(threshold_minutes=0),
        tool_result_store=tool_result_store,
        max_steps=2,
    )


def _build_naive_loop(
    provider: _UsageTrackingProvider, transcript: Transcript,
) -> AgentLoop:
    """Huge budget + no compactor + no externalization + no microcompact."""
    budget = ContextBudget(
        max_tokens=_NAIVE_BUDGET_TOKENS,
        reserved_output_tokens=_NAIVE_RESERVED_OUTPUT,
    )
    builder = ContextBuilder(budget=budget)  # no tool_result_store passed
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    return AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=None,
        # huge threshold → microcompact never fires within this benchmark run
        microcompactor=MicroCompactor(threshold_minutes=10**9),
        tool_result_store=None,
        max_steps=2,
    )


# ---------------------------------------------------------------------------
# Real-API driver
# ---------------------------------------------------------------------------
def _build_provider(
    *, model: str, api_key: str, base_url: str | None
) -> OpenAIProvider:
    return OpenAIProvider(
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_tokens=512,
    )


def _drive(
    label: str, loop: AgentLoop,
) -> list[str]:
    answers: list[str] = []
    for question in _USER_QUESTIONS:
        result = loop.run(question)
        answers.append(result.answer or "(no answer)")
    return answers


def _usage_to_cost(
    usage: _UsageRecord, in_price: float, out_price: float,
) -> dict[str, Any]:
    in_cost = (usage.input_tokens / 1_000_000) * in_price
    out_cost = (usage.output_tokens / 1_000_000) * out_price
    return {
        "calls": usage.calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_input_tokens": usage.cache_read_input_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        "input_cost_usd": round(in_cost, 6),
        "output_cost_usd": round(out_cost, 6),
        "total_cost_usd": round(in_cost + out_cost, 6),
        "per_call": usage.per_call,
    }


def _api_key_and_base() -> tuple[str, str | None] | None:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key, os.environ.get("OPENAI_BASE_URL")
    key = os.environ.get("DASHSCOPE_API_KEY")
    if key:
        return key, os.environ.get("OPENAI_BASE_URL") or _DASHSCOPE_BASE_URL
    return None


def _resolve_prices(
    *,
    model: str,
    in_override: float | None,
    out_override: float | None,
) -> tuple[float, float, str]:
    if in_override is not None and out_override is not None:
        return in_override, out_override, "explicit-flags"
    table_hit = _MODEL_PRICES.get(model)
    if table_hit is not None:
        return table_hit[0], table_hit[1], "model-table"
    return 0.50, 1.50, "fallback-default"  # conservative neutral guess


def _render_markdown(payload: dict[str, Any]) -> str:
    cfg = payload["config"]
    f = payload["full"]
    n = payload["naive"]
    s = payload["savings"]
    lines = [
        "# Benchmark 3 — Real-API Token-Cost Comparison",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Model: `{cfg['model']}`  ·  "
        f"Prices (USD per 1M tokens): in=${cfg['input_price_per_1m']}, "
        f"out=${cfg['output_price_per_1m']} (`{cfg['price_source']}`)",
        "",
        "## Scenario",
        "",
        f"- Seeded transcript: **{cfg['tool_exchanges']}** tool exchanges "
        f"× {cfg['tool_result_chars_each']:,} chars each",
        f"- Driven turns:      **{cfg['turns']}**",
        "- Full pipeline:     compactor ON + tool-result-store ON + "
        "microcompact ON, "
        f"budget={cfg['full_budget_tokens']:,} tokens",
        "- Naive baseline:    compactor OFF + tool-result-store OFF + "
        "microcompact OFF, "
        f"budget={cfg['naive_budget_tokens']:,} tokens",
        "",
        "## Token & cost totals",
        "",
        "| Variant | Calls | Input tokens | Output tokens | Total USD |",
        "| ------- | ----- | ------------ | ------------- | --------- |",
        f"| full    | {f['calls']} | {f['input_tokens']:,} | "
        f"{f['output_tokens']:,} | ${f['total_cost_usd']:.6f} |",
        f"| naive   | {n['calls']} | {n['input_tokens']:,} | "
        f"{n['output_tokens']:,} | ${n['total_cost_usd']:.6f} |",
        "",
        "## Savings",
        "",
        f"- Input tokens saved:  **{s['input_tokens_saved']:,}** "
        f"({s['input_tokens_saved_pct']}%)",
        f"- Output tokens saved: **{s['output_tokens_saved']:,}** "
        f"({s['output_tokens_saved_pct']}%)",
        f"- USD saved:           **${s['usd_saved']:.6f}** "
        f"({s['usd_saved_pct']}%)",
        "",
        "## Per-call token traces",
        "",
        "### full",
        "",
        "```json",
        json.dumps(f["per_call"], indent=2),
        "```",
        "",
        "### naive",
        "",
        "```json",
        json.dumps(n["per_call"], indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bench_openai_cost",
        description=(
            "Real-API token-cost comparison: full pipeline vs naive baseline. "
            "Requires --confirm-api-call and either OPENAI_API_KEY or "
            "DASHSCOPE_API_KEY."
        ),
    )
    p.add_argument("--confirm-api-call", action="store_true")
    p.add_argument("--model", default=os.environ.get(
        "SIMPLE_AGENT_MODEL", _DEFAULT_MODEL,
    ))
    p.add_argument("--input-price-per-1m", type=float, default=None)
    p.add_argument("--output-price-per-1m", type=float, default=None)
    p.add_argument(
        "--summarizer-mode",
        choices=("rule", "llm"),
        default="rule",
        help=(
            "Summarizer used by the Full configuration. 'rule' (default) "
            "uses RuleBasedSummarizer (zero extra API cost); 'llm' wraps "
            "the same usage-tracked provider so summarization API calls "
            "are billed into the total."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.confirm_api_call:
        print(
            "Refusing to spend real tokens without --confirm-api-call.",
            file=sys.stderr,
        )
        return 2
    key_pack = _api_key_and_base()
    if key_pack is None:
        print(
            "Set OPENAI_API_KEY or DASHSCOPE_API_KEY before running.",
            file=sys.stderr,
        )
        return 3
    api_key, base_url = key_pack
    in_price, out_price, price_source = _resolve_prices(
        model=args.model,
        in_override=args.input_price_per_1m,
        out_override=args.output_price_per_1m,
    )

    # Independent providers so the per-loop usage counter stays isolated.
    inner_full = _build_provider(
        model=args.model, api_key=api_key, base_url=base_url,
    )
    inner_naive = _build_provider(
        model=args.model, api_key=api_key, base_url=base_url,
    )
    full_provider = _UsageTrackingProvider(inner_full)
    naive_provider = _UsageTrackingProvider(inner_naive)

    full_loop = _build_full_loop(
        full_provider,
        _seeded_transcript(),
        summarizer_mode=args.summarizer_mode,
    )
    naive_loop = _build_naive_loop(naive_provider, _seeded_transcript())

    print(
        f"[bench3] running {_TURNS} turns × 2 loops on {args.model} "
        f"(summarizer={args.summarizer_mode})…"
    )
    full_answers = _drive("full", full_loop)
    print(f"[bench3]   full   done: {full_provider.usage.calls} calls, "
          f"{full_provider.usage.input_tokens:,} in + "
          f"{full_provider.usage.output_tokens:,} out tokens")
    naive_answers = _drive("naive", naive_loop)
    print(f"[bench3]   naive  done: {naive_provider.usage.calls} calls, "
          f"{naive_provider.usage.input_tokens:,} in + "
          f"{naive_provider.usage.output_tokens:,} out tokens")

    full_cost = _usage_to_cost(full_provider.usage, in_price, out_price)
    naive_cost = _usage_to_cost(naive_provider.usage, in_price, out_price)

    def _pct(saved: int, baseline: int) -> float:
        return round(100.0 * saved / baseline, 2) if baseline > 0 else 0.0

    savings = {
        "input_tokens_saved":  naive_cost["input_tokens"]  - full_cost["input_tokens"],
        "output_tokens_saved": naive_cost["output_tokens"] - full_cost["output_tokens"],
        "usd_saved":           round(
            naive_cost["total_cost_usd"] - full_cost["total_cost_usd"], 6,
        ),
        "input_tokens_saved_pct": _pct(
            naive_cost["input_tokens"] - full_cost["input_tokens"],
            naive_cost["input_tokens"],
        ),
        "output_tokens_saved_pct": _pct(
            naive_cost["output_tokens"] - full_cost["output_tokens"],
            naive_cost["output_tokens"],
        ),
        "usd_saved_pct": _pct(
            int((naive_cost["total_cost_usd"] - full_cost["total_cost_usd"]) * 1_000_000),
            int(naive_cost["total_cost_usd"] * 1_000_000),
        ),
    }

    payload = {
        "scenario": "5-turn real-API conversation: full pipeline vs naive baseline",
        "config": {
            "model": args.model,
            "input_price_per_1m": in_price,
            "output_price_per_1m": out_price,
            "price_source": price_source,
            "tool_exchanges": _TOOL_EXCHANGE_COUNT,
            "tool_result_chars_each": _TOOL_RESULT_CHARS,
            "turns": _TURNS,
            "full_budget_tokens": _FULL_BUDGET_TOKENS,
            "naive_budget_tokens": _NAIVE_BUDGET_TOKENS,
            "summarizer_mode": args.summarizer_mode,
        },
        "full": full_cost,
        "naive": naive_cost,
        "savings": savings,
        "answers_preview": {
            "full":  [a[:80] for a in full_answers],
            "naive": [a[:80] for a in naive_answers],
        },
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path, md_path = _result_paths(args.summarizer_mode)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    tag = f"bench3:{args.summarizer_mode}"
    print(
        f"[{tag}] tokens   in: "
        f"{naive_cost['input_tokens']:,} → {full_cost['input_tokens']:,}  "
        f"(saved {savings['input_tokens_saved']:,} = "
        f"{savings['input_tokens_saved_pct']}%)"
    )
    print(
        f"[{tag}] tokens  out: "
        f"{naive_cost['output_tokens']:,} → {full_cost['output_tokens']:,}  "
        f"(saved {savings['output_tokens_saved']:,} = "
        f"{savings['output_tokens_saved_pct']}%)"
    )
    print(
        f"[{tag}] cost   USD: "
        f"${naive_cost['total_cost_usd']:.6f} → ${full_cost['total_cost_usd']:.6f}  "
        f"(saved ${savings['usd_saved']:.6f} = {savings['usd_saved_pct']}%)"
    )
    print(f"[{tag}] artifacts: {json_path.name}, {md_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
