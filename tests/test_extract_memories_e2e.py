"""End-to-end tests for extraction wired into AgentLoop.

Builds a real AgentLoop with a scripted MockProvider and verifies that
_run_stop_hooks fires extraction and updates MetricsCollector.
"""

from __future__ import annotations

from pathlib import Path

from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopStatus
from simple_coding_agent.memory import ProjectMemory
from simple_coding_agent.metrics import MetricsCollector
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tool_registry_factory import build_default_registry
from simple_coding_agent.tools import ToolExecutor
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_loop(
    tmp_path: Path,
    *,
    main_responses: list,
    extract_memories_enabled: bool = True,
) -> tuple[AgentLoop, MetricsCollector, ProjectMemory]:
    """Wire a minimal AgentLoop for extraction tests."""
    memory_dir = tmp_path / "memory"
    project_memory = ProjectMemory(str(memory_dir))

    provider = MockProvider(main_responses)
    transcript = Transcript()
    registry = build_default_registry(tmp_path, transcript=transcript)
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=10_000, reserved_output_tokens=512)
    builder = ContextBuilder(budget=budget, project_memory=project_memory)
    metrics = MetricsCollector()

    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        project_memory=project_memory,
        metrics=metrics,
        extract_memories_enabled=extract_memories_enabled,
    )
    return loop, metrics, project_memory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_e2e_extraction_writes_memory(tmp_path):
    """Full loop run: main agent answers, extraction runner writes one memory file."""
    memory_dir = tmp_path / "memory"

    responses = [
        # Main agent: direct answer with no write_memory_entry calls
        MockProvider.direct_answer("Task done!"),
        # Extraction runner turn 1: write a memory entry
        MockProvider.tool_call(
            "write_memory_entry",
            {
                "type": "user",
                "id": "test-insight",
                "name": "test insight",
                "description": "A user preference captured during extraction",
                "body": "The user prefers concise answers",
            },
            id="ex_tc_1",
        ),
        # Extraction runner turn 2: end extraction
        MockProvider.direct_answer("Memory saved."),
    ]

    loop, metrics, _ = _build_loop(tmp_path, main_responses=responses)
    result = loop.run("Tell me something.")

    assert result.status == LoopStatus.COMPLETED
    assert metrics.extract_invocations == 1
    assert metrics.extract_writes == 1

    # Memory file must exist
    mem_file = memory_dir / "test-insight.md"
    assert mem_file.exists(), f"Expected {mem_file} to exist after extraction"


def test_metrics_incremented(tmp_path):
    """extract_invocations and extract_writes are tracked per successful run."""
    responses = [
        MockProvider.direct_answer("All good."),
        # Extraction runner: write two memories in one run
        MockProvider.tool_call(
            "write_memory_entry",
            {
                "type": "feedback",
                "id": "mem-a",
                "name": "mem A",
                "description": "first memory",
                "body": "prefer X over Y",
            },
            id="ex_1",
        ),
        MockProvider.tool_call(
            "write_memory_entry",
            {
                "type": "project",
                "id": "mem-b",
                "name": "mem B",
                "description": "second memory",
                "body": "project uses FastAPI",
            },
            id="ex_2",
        ),
        MockProvider.direct_answer("Done."),
    ]

    loop, metrics, _ = _build_loop(tmp_path, main_responses=responses)
    loop.run("Status?")

    assert metrics.extract_invocations == 1
    assert metrics.extract_writes == 2


def test_extract_memories_disabled_by_default(tmp_path):
    """When extract_memories_enabled is not set, no extraction occurs."""
    responses = [
        MockProvider.direct_answer("Done."),
        # These would be consumed if extraction ran — but it shouldn't
        MockProvider.direct_answer("Should never be reached."),
    ]
    loop, metrics, _ = _build_loop(
        tmp_path, main_responses=responses, extract_memories_enabled=False
    )
    loop.run("Hello.")

    assert metrics.extract_invocations == 0
    # Provider should have only consumed one response
    assert loop._provider._index == 1  # only main agent response consumed


def test_in_progress_flag_blocks_reentrant_extraction(tmp_path):
    """Regression (auto-memory-overhaul finding #3): the loop must pass its real
    _extraction_in_progress flag into gate 4, not a hardcoded False.

    Pre-setting the flag simulates being already inside an extraction; gate 4
    must then short-circuit. Before the fix the loop hardcoded False, so the
    flag was dead and extraction ran regardless.
    """
    responses = [
        MockProvider.direct_answer("Task done!"),
        # Consumed by the extraction runner only if it (incorrectly) runs:
        MockProvider.tool_call(
            "write_memory_entry",
            {
                "type": "user",
                "id": "should-not-write",
                "name": "x",
                "description": "x",
                "body": "x",
            },
            id="ex_tc_1",
        ),
        MockProvider.direct_answer("Memory saved."),
    ]
    loop, metrics, _ = _build_loop(tmp_path, main_responses=responses)
    loop._extraction_in_progress = True  # simulate already inside an extraction

    loop.run("Tell me something.")

    assert metrics.extract_invocations == 0  # gate 4 short-circuits
    assert loop._provider._index == 1  # only the main answer consumed
    assert not (tmp_path / "memory" / "should-not-write.md").exists()
