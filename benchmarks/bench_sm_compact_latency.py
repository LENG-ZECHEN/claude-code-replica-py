"""Benchmark 4: SM-compact latency — dual-arm (deterministic + real-API).

Goal: replace the never-existed "98.7%" compaction-time saving claim with
disclosed, reproducible wall-clock numbers.

Two arms:

  (a) DETERMINISTIC (always runs):
      RuleBasedSummarizer full recompute vs O(0) SessionMemorySummarizer
      warm reuse.  No API, no network, fully reproducible.  This is the
      defensible floor.

  (b) REAL-API (gated behind --confirm-api-call + key):
      LLMSummarizer wall-clock vs ~0 SM reuse on DashScope qwen-plus-latest.
      Drifts run-to-run.  Requires OPENAI_API_KEY or DASHSCOPE_API_KEY.

JSON includes raw per-run perf_counter timings (median + p90) and a
``latency_source`` field on each arm disclosing where each number came from.

Honesty rule: never conflate the two arms.  Deterministic numbers are the
reproducible floor; real-API numbers are the realistic headline.  Both are
labeled.  No fabricated percentages.

Source mapping:
  sessionMemoryCompact.ts:498  — "SM-compact has no compact-API-call"
  sessionMemoryCompact.ts:58-60 — DEFAULT_SM_COMPACT_CONFIG (minTokens=10_000,
      minTextBlockMessages=5, maxTokens=40_000)
  compact.ts:1136 streamCompactSummary — the LLM call SM warm path SKIPS

Run:
    python -m benchmarks.bench_sm_compact_latency                  # deterministic only
    DASHSCOPE_API_KEY=sk-... python -m benchmarks.bench_sm_compact_latency \\
        --confirm-api-call                                          # both arms
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from simple_coding_agent.compact import (
    ContextCompactor,
    LLMSummarizer,
    RuleBasedSummarizer,
    SessionMemorySummarizer,
)
from simple_coding_agent.context import ContextBudget
from simple_coding_agent.models import Message
from simple_coding_agent.session_memory_state import _SECTION_NAMES, SessionMemoryState
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Scale knobs
# ---------------------------------------------------------------------------

# Large enough that RuleBasedSummarizer does real work (mirrors SM minTokens=10k).
_MSG_PAIRS = 20
_MSG_BODY_CHARS = 500  # ~125 tokens each; 20 pairs ≈ 2500 tokens to summarize

_RUNS = 50
_KEEP_RECENT = 4
_COMPACT_THRESHOLD = 0.5

# DashScope endpoint (mirrors bench_openai_cost.py line 114)
_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen-plus-latest"

_RESULTS_DIR = Path(__file__).resolve().parent / "_results"
_JSON_PATH = _RESULTS_DIR / "04_sm_compact_latency.json"
_MD_PATH = _RESULTS_DIR / "04_sm_compact_latency.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_warm_state() -> SessionMemoryState:
    """Return a pre-warmed SM state with non-trivial content (mirrors stop-hook output)."""
    return SessionMemoryState(
        sections=tuple(
            (name, f"Session summary content for: {name}. " * 10)
            for name in _SECTION_NAMES
        )
    )


def _build_transcript() -> Transcript:
    """Seed a transcript large enough that RuleBasedSummarizer does real work."""
    t = Transcript()
    for i in range(_MSG_PAIRS):
        t.append(Message.user(f"User question {i}: " + "context " * (_MSG_BODY_CHARS // 8)))
        t.append(Message.assistant(f"Answer {i}: " + "detail " * (_MSG_BODY_CHARS // 7)))
    return t


def _measure_arm(summarizer: Any, runs: int) -> dict[str, Any]:
    """Measure wall-clock ms for `runs` compact() calls using `summarizer`."""
    times_ms: list[float] = []
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    for _ in range(runs):
        compactor = ContextCompactor(
            keep_recent=_KEEP_RECENT,
            compact_threshold=_COMPACT_THRESHOLD,
            summarizer=summarizer,
        )
        transcript = _build_transcript()
        t0 = time.perf_counter()
        compactor.compact(transcript, budget)
        times_ms.append((time.perf_counter() - t0) * 1000)
    sorted_times = sorted(times_ms)
    p90_idx = max(0, int(len(sorted_times) * 0.9) - 1)
    return {
        "runs": runs,
        "median_ms": round(statistics.median(times_ms), 4),
        "p90_ms": round(sorted_times[p90_idx], 4),
        "min_ms": round(min(times_ms), 4),
        "max_ms": round(max(times_ms), 4),
        "raw_ms": [round(t, 4) for t in times_ms],
    }


# ---------------------------------------------------------------------------
# Arm (a): deterministic — no API
# ---------------------------------------------------------------------------

def _run_deterministic(runs: int = _RUNS) -> dict[str, Any]:
    """Run the deterministic arm: RuleBasedSummarizer vs O(0) SM warm reuse.

    Both summarizers are pure-Python, no network, no API key.  The slow arm
    runs RuleBasedSummarizer (real 9-section extraction); the fast arm returns
    state.render() immediately with zero compute overhead.

    Source: sessionMemoryCompact.ts:498 — O(0) cost confirmed in TS source.
    """
    warm_state = _make_warm_state()
    rule_summarizer = RuleBasedSummarizer()
    sm_summarizer = SessionMemorySummarizer(warm_state, fallback=rule_summarizer)

    full_arm = _measure_arm(rule_summarizer, runs)
    reuse_arm = _measure_arm(sm_summarizer, runs)

    return {
        "generated": datetime.now(UTC).isoformat(),
        "runs_per_arm": runs,
        "arms": {
            "deterministic": {
                "full_arm": full_arm,
                "reuse_arm": reuse_arm,
                "latency_source": (
                    "deterministic: RuleBasedSummarizer recompute vs "
                    "SessionMemorySummarizer reuse, perf_counter, no network"
                ),
            },
        },
    }


# ---------------------------------------------------------------------------
# Arm (b): real-API (gated)
# ---------------------------------------------------------------------------

def _api_key_and_base() -> tuple[str, str] | None:
    """Return (api_key, base_url) or None if no key is available."""
    if dashscope_key := os.environ.get("DASHSCOPE_API_KEY"):
        return dashscope_key, _DASHSCOPE_BASE_URL
    if openai_key := os.environ.get("OPENAI_API_KEY"):
        return openai_key, "https://api.openai.com/v1"
    return None


def _run_real_api(model: str, api_key: str, base_url: str, runs: int = _RUNS) -> dict[str, Any]:
    """Run the real-API arm: LLMSummarizer wall-clock vs ~0 SM reuse.

    This arm makes real API calls and drifts run-to-run.  Only the full arm
    calls the API; the reuse arm returns the prewarmed state immediately.
    """
    from simple_coding_agent.provider import OpenAIProvider

    warm_state = _make_warm_state()
    provider = OpenAIProvider(api_key=api_key, base_url=base_url, model=model)
    llm_summarizer = LLMSummarizer(provider)
    rule_fallback = RuleBasedSummarizer()
    sm_summarizer = SessionMemorySummarizer(warm_state, fallback=rule_fallback)

    full_arm = _measure_arm(llm_summarizer, runs)
    # Reuse arm doesn't call the API — measure its O(0) cost
    reuse_arm = _measure_arm(sm_summarizer, runs)

    return {
        "full_arm": full_arm,
        "reuse_arm": reuse_arm,
        "latency_source": (
            f"live API: DashScope {model} LLMSummarizer wall-clock, "
            "drifts run-to-run"
        ),
        "model": model,
        "api_base": base_url,
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _render_markdown(payload: dict[str, Any]) -> str:
    arms = payload["arms"]
    det = arms["deterministic"]
    full = det["full_arm"]
    reuse = det["reuse_arm"]

    lines = [
        "# Benchmark 4 — SM-compact Latency (dual-arm)",
        "",
        f"Generated: {payload['generated']}",
        f"Runs per arm: {payload['runs_per_arm']}",
        "",
        "## Deterministic arm (no API, reproducible floor)",
        "",
        f"> Source: {det['latency_source']}",
        "",
        "### Full summarization (RuleBasedSummarizer recompute)",
        "",
        f"- median: **{full['median_ms']:.3f} ms**",
        f"- p90:    {full['p90_ms']:.3f} ms",
        f"- min:    {full['min_ms']:.3f} ms",
        f"- max:    {full['max_ms']:.3f} ms",
        "",
        "### SM warm reuse (SessionMemorySummarizer, O(0))",
        "",
        f"- median: **{reuse['median_ms']:.3f} ms**",
        f"- p90:    {reuse['p90_ms']:.3f} ms",
        f"- min:    {reuse['min_ms']:.3f} ms",
        f"- max:    {reuse['max_ms']:.3f} ms",
        "",
        "### Speedup (deterministic floor)",
        "",
    ]
    if reuse["median_ms"] > 0:
        ratio = full["median_ms"] / reuse["median_ms"]
        lines.append(f"- full / reuse = **{ratio:.1f}×** (median)")
    else:
        lines.append("- reuse median ≈ 0 ms (below timer resolution)")
    lines.append("")

    if "real_api" in arms:
        api = arms["real_api"]
        api_full = api["full_arm"]
        api_reuse = api["reuse_arm"]
        lines += [
            "## Real-API arm (live DashScope, drifts run-to-run)",
            "",
            f"> Source: {api['latency_source']}",
            f"> Model: {api.get('model', 'unknown')}",
            "",
            "### LLMSummarizer wall-clock",
            "",
            f"- median: **{api_full['median_ms']:.3f} ms**",
            f"- p90:    {api_full['p90_ms']:.3f} ms",
            "",
            "### SM warm reuse (~0 ms)",
            "",
            f"- median: **{api_reuse['median_ms']:.3f} ms**",
            f"- p90:    {api_reuse['p90_ms']:.3f} ms",
            "",
            "> Note: real-API numbers drift run-to-run due to network latency and",
            "> model load. The deterministic arm above is the reproducible floor.",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bench_sm_compact_latency",
        description=(
            "SM-compact latency benchmark. "
            "Deterministic arm always runs. "
            "Real-API arm requires --confirm-api-call + DASHSCOPE_API_KEY or OPENAI_API_KEY."
        ),
    )
    p.add_argument("--confirm-api-call", action="store_true")
    p.add_argument("--model", default=_DEFAULT_MODEL)
    p.add_argument("--runs", type=int, default=_RUNS)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    payload = _run_deterministic(runs=args.runs)

    if args.confirm_api_call:
        key_pack = _api_key_and_base()
        if key_pack is None:
            print(
                "Set OPENAI_API_KEY or DASHSCOPE_API_KEY before running the real-API arm.",
                file=sys.stderr,
            )
            return 3
        api_key, base_url = key_pack
        print(f"[bench4] running real-API arm on {args.model}…", file=sys.stderr)
        real_result = _run_real_api(
            model=args.model,
            api_key=api_key,
            base_url=base_url,
            runs=args.runs,
        )
        payload["arms"]["real_api"] = real_result
    elif any(arg in (argv or []) for arg in ["--confirm-api-call"]):
        # --confirm-api-call present but no key — handled above
        pass

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _JSON_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _MD_PATH.write_text(_render_markdown(payload), encoding="utf-8")

    det = payload["arms"]["deterministic"]
    full_ms = det["full_arm"]["median_ms"]
    reuse_ms = det["reuse_arm"]["median_ms"]
    print(
        f"[bench4] deterministic: full={full_ms:.3f}ms -> reuse={reuse_ms:.3f}ms "
        f"(median of {args.runs})"
    )
    print(f"[bench4] artifacts: {_JSON_PATH.name}, {_MD_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
