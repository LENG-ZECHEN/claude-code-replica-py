"""M3 (auto-memory-overhaul): end-to-end write_memory_entry tests.

Written before implementation (TDD — RED phase).

Coverage:
  4. test_e2e_model_emitted_write_lands_on_disk
     — MockProvider scripts write_memory_entry tool_use -> .md on disk
     — frontmatter and MEMORY.md index are correct
  5. test_remember_repl_uses_shared_project_memory
     — /remember write reaches the same ProjectMemory as AgentLoop
"""

from __future__ import annotations

from pathlib import Path

from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop, LoopStatus
from simple_coding_agent.memory import MemoryEntry, MemoryType, ProjectMemory
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tools import ToolExecutor, ToolRegistry
from simple_coding_agent.transcript import Transcript


def _make_loop(
    provider: MockProvider,
    project_memory: ProjectMemory | None,
) -> AgentLoop:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    transcript = Transcript()
    context_builder = ContextBuilder(budget=budget, project_memory=project_memory)
    return AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=context_builder,
        budget=budget,
        registry=registry,
        project_memory=project_memory,
    )


def test_e2e_model_emitted_write_lands_on_disk(tmp_path: Path) -> None:
    pm = ProjectMemory(str(tmp_path))
    responses = [
        MockProvider.tool_call(
            "write_memory_entry",
            {
                "type": "feedback",
                "id": "test-entry",
                "name": "test",
                "description": "desc",
                "body": "body",
            },
            id="tu_write_mem",
        ),
        MockProvider.direct_answer("Done."),
    ]
    loop = _make_loop(MockProvider(responses), pm)
    result = loop.run("hello")

    assert result.status == LoopStatus.COMPLETED

    md_file = tmp_path / "test-entry.md"
    assert md_file.exists()
    content = md_file.read_text(encoding="utf-8")
    assert "name: test" in content
    assert "type: feedback" in content
    assert "description: desc" in content

    memory_index = tmp_path / "MEMORY.md"
    assert memory_index.exists()
    assert "test-entry" in memory_index.read_text(encoding="utf-8")


def test_remember_repl_uses_shared_project_memory(tmp_path: Path) -> None:
    """The same ProjectMemory instance backs both AgentLoop and /remember."""
    pm = ProjectMemory(str(tmp_path))
    loop = _make_loop(MockProvider([MockProvider.direct_answer("Ack.")]), pm)

    # Verify AgentLoop holds the exact same instance we created
    assert loop._project_memory is pm

    # Write via the shared pm (as /remember would via loop._project_memory)
    entry = MemoryEntry(
        name="shared-test",
        body="shared body",
        type=MemoryType.FEEDBACK,
        id="shared-test",
    )
    loop._project_memory.save(entry)  # type: ignore[union-attr]

    # Entry is visible via pm — single store
    assert (tmp_path / "shared-test.md").exists()
    entries = pm.all()
    assert any(e.id == "shared-test" for e in entries)
