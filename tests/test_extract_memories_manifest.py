"""Regression test for auto-memory-overhaul review finding #6.

ExtractMemoriesRunner must build its "existing memories (do not duplicate)"
manifest by scanning the .md files via memdir, not by reading a possibly-absent
or stale MEMORY.md prefix (the M4 stub).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from simple_coding_agent.extract_memories import ExtractMemoriesRunner
from simple_coding_agent.provider import MockProvider, ProviderResponse
from simple_coding_agent.tools import ToolRegistry


class _PromptRecorder:
    """Minimal Provider stub: records the prompt messages and ends the turn."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] | None = None

    def call(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        self.messages = messages
        return MockProvider.direct_answer("nothing worth saving")


def _write_memory_file(directory: Path, rel_id: str, name: str, desc: str) -> None:
    path = directory / f"{rel_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ntype: user\ndescription: {desc}\n"
        f"created_at: 2026-01-01T00:00:00+00:00\n---\n\nbody\n",
        encoding="utf-8",
    )


def test_runner_scans_md_files_not_absent_memory_md(tmp_path: Path) -> None:
    # Memory files exist on disk, but the MEMORY.md manifest does NOT. The old
    # M4 stub read MEMORY.md[:2000] and would report "(no memories yet)"; the
    # fix scans the .md files directly via the canonical memdir formatter.
    _write_memory_file(tmp_path, "user/role", "My role", "backend developer")
    assert not (tmp_path / "MEMORY.md").exists()

    rec = _PromptRecorder()
    runner = ExtractMemoriesRunner(
        provider=rec,
        memory_dir=tmp_path,
        system_prompt="sys",
        base_messages=[],
        tool_registry=ToolRegistry(),
    )
    runner.run(1)

    assert rec.messages is not None
    prompt = str(rec.messages[0]["content"])
    assert "My role" in prompt
    assert "user/role.md" in prompt
    assert "(no memories yet)" not in prompt
