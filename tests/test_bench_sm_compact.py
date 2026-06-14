"""M4 tests: SM-compact latency benchmark + trace reused field.

Verifies:
  1. measured_reuse_ms < full_arm_ms using a slow fake summarizer.
  2. StderrTracer emits reused=True on the compact channel for a warm SM path.
  3. StderrTracer emits reused=False on the compact channel for a cold SM path.
  4. The bench module exists and its _run_deterministic() returns the expected keys.
"""

from __future__ import annotations

import importlib.util
import io
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from simple_coding_agent.compact import (
    ContextCompactor,
    RuleBasedSummarizer,
    SessionMemorySummarizer,
)
from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.models import Message
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.session_memory_state import _SECTION_NAMES, SessionMemoryState
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.trace import StderrTracer
from simple_coding_agent.transcript import Transcript

_BENCH_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "bench_sm_compact_latency.py"


def _load_bench_module() -> Any:
    """Import bench_sm_compact_latency.py as a module for testing."""
    spec = importlib.util.spec_from_file_location("bench_sm_compact_latency", _BENCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_sm_compact_latency"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_warm_state() -> SessionMemoryState:
    return SessionMemoryState(
        sections=tuple((name, f"Content for {name}") for name in _SECTION_NAMES)
    )


def _make_transcript(n: int = 5) -> Transcript:
    t = Transcript()
    for i in range(n):
        t.append(Message.user(f"user {i}"))
        t.append(Message.assistant(f"asst {i}"))
    return t


class _SlowSummarizer:
    """Summarizer that sleeps a fixed delay — ensures full_arm_ms is measurable."""

    def __init__(self, delay_s: float = 0.005) -> None:
        self._delay = delay_s

    def summarize(self, messages: list[Message]) -> str:
        time.sleep(self._delay)
        return "slow summary"


# ---------------------------------------------------------------------------
# 1. measured_reuse_ms < full_arm_ms (core benchmark assertion)
# ---------------------------------------------------------------------------


def test_measured_reuse_ms_less_than_full_arm_ms() -> None:
    """SM reuse arm is faster than full summarization arm with injected delay."""
    R = 10
    delay_s = 0.005  # 5ms per call — enough to be measurable

    slow_summarizer = _SlowSummarizer(delay_s)
    warm_state = _make_warm_state()
    sm_summarizer = SessionMemorySummarizer(warm_state, fallback=slow_summarizer)

    # Full arm — slow summarizer is called every run
    full_times: list[float] = []
    for _ in range(R):
        t0 = time.perf_counter()
        compactor = ContextCompactor(keep_recent=0, summarizer=slow_summarizer)
        transcript = _make_transcript()
        budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8192)
        compactor.compact(transcript, budget)
        full_times.append((time.perf_counter() - t0) * 1000)

    # Reuse arm — SM warm state returns immediately
    reuse_times: list[float] = []
    for _ in range(R):
        t0 = time.perf_counter()
        compactor = ContextCompactor(keep_recent=0, summarizer=sm_summarizer)
        transcript = _make_transcript()
        budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8192)
        compactor.compact(transcript, budget)
        reuse_times.append((time.perf_counter() - t0) * 1000)

    full_median = statistics.median(full_times)
    reuse_median = statistics.median(reuse_times)

    assert reuse_median < full_median, (
        f"Expected reuse_median ({reuse_median:.3f}ms) < full_median ({full_median:.3f}ms)"
    )


# ---------------------------------------------------------------------------
# 2. Trace emits reused=True on compact channel for warm SM path
# ---------------------------------------------------------------------------


def test_compact_trace_reused_true_for_warm_sm() -> None:
    """_force_compact with warm SM emits reused=True on the compact trace channel."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    warm_state = _make_warm_state()
    provider = MockProvider([MockProvider.direct_answer("done")])
    transcript = _make_transcript()
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=8192, reserved_output_tokens=4096)
    builder = ContextBuilder(budget=budget)
    metrics = MetricsCollector()
    compactor = ContextCompactor(keep_recent=0, summarizer=RuleBasedSummarizer())
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        session_memory_enabled=True,
        metrics=metrics,
        tracer=tracer,
    )
    loop._session_memory_state = warm_state

    loop._force_compact()

    output = buf.getvalue()
    assert "[trace] [compact]" in output
    assert "reused=True" in output


# ---------------------------------------------------------------------------
# 3. Trace emits reused=False on compact channel for cold SM path
# ---------------------------------------------------------------------------


def test_compact_trace_reused_false_for_cold_sm() -> None:
    """_force_compact with cold SM emits reused=False on the compact trace channel."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    provider = MockProvider([MockProvider.direct_answer("done")])
    transcript = _make_transcript()
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=8192, reserved_output_tokens=4096)
    builder = ContextBuilder(budget=budget)
    metrics = MetricsCollector()
    compactor = ContextCompactor(keep_recent=0, summarizer=RuleBasedSummarizer())
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        compactor=compactor,
        session_memory_enabled=True,
        metrics=metrics,
        tracer=tracer,
    )
    # SM state is cold (empty) by default
    assert loop._session_memory_state.is_empty

    loop._force_compact()

    output = buf.getvalue()
    assert "[trace] [compact]" in output
    assert "reused=False" in output


# ---------------------------------------------------------------------------
# 4. Bench module structure: _run_deterministic returns expected keys
# ---------------------------------------------------------------------------


def test_bench_module_run_deterministic_returns_expected_keys() -> None:
    """bench_sm_compact_latency._run_deterministic() returns dict with required keys."""
    bench = _load_bench_module()
    try:
        result = bench._run_deterministic(runs=5)
    finally:
        sys.modules.pop("bench_sm_compact_latency", None)

    assert "arms" in result
    arms = result["arms"]
    assert "deterministic" in arms
    det = arms["deterministic"]
    assert "full_arm" in det
    assert "reuse_arm" in det
    assert "latency_source" in det

    full_arm = det["full_arm"]
    reuse_arm = det["reuse_arm"]
    assert full_arm["median_ms"] > reuse_arm["median_ms"], (
        f"Expected full_arm median ({full_arm['median_ms']:.3f}ms) > "
        f"reuse_arm median ({reuse_arm['median_ms']:.3f}ms)"
    )
