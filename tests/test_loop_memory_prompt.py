"""M3 (auto-memory-overhaul): system prompt teaching section tests.

Written before implementation (TDD — RED phase).

Coverage:
  1. test_memory_management_section_present
     — ## Memory Management in system prompt when project_memory provided
  2. test_memory_management_section_absent_without_project_memory
     — section NOT present when project_memory is None
  3. test_memory_management_section_before_memory_snippets
     — ## Memory Management appears before ## Memory snippets
"""

from __future__ import annotations

from pathlib import Path

from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.memory import ProjectMemory
from simple_coding_agent.models import Message
from simple_coding_agent.transcript import Transcript


def _build(
    tmp_path: Path | None,
    memory_snippets: list[str] | None = None,
) -> str:
    pm = ProjectMemory(str(tmp_path)) if tmp_path is not None else None
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    builder = ContextBuilder(budget=budget, project_memory=pm)
    transcript = Transcript()
    transcript.append(Message.user("hello"))
    built = builder.build(transcript, system="base system", memory_snippets=memory_snippets)
    return built.system


def test_memory_management_section_present(tmp_path: Path) -> None:
    system = _build(tmp_path)
    assert "## Memory Management" in system


def test_memory_management_section_absent_without_project_memory() -> None:
    system = _build(None)
    assert "## Memory Management" not in system


def test_memory_management_section_before_memory_snippets(tmp_path: Path) -> None:
    system = _build(tmp_path, memory_snippets=["snippet one"])
    assert "## Memory Management" in system
    assert "## Memory\n" in system
    assert system.index("## Memory Management") < system.index("## Memory\n")
