"""Tests for AgentLoop sideQuery memory injection (M7).

Verifies that ATTACHMENT_MEMORY messages are injected into the transcript
before Provider.call(), that already_surfaced deduplication works, and
that session_bytes_used accumulates correctly.
"""
from __future__ import annotations

from pathlib import Path

from simple_coding_agent.context import ContextBudget, ContextBuilder
from simple_coding_agent.loop import AgentLoop
from simple_coding_agent.memory import ProjectMemory
from simple_coding_agent.models import MessageType
from simple_coding_agent.provider import MockProvider
from simple_coding_agent.tool_registry_factory import build_default_registry
from simple_coding_agent.tools import ToolExecutor
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_memory(
    directory: Path,
    entry_id: str,
    name: str = "Test",
    desc: str = "test memory",
) -> None:
    file_path = directory / f"{entry_id}.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        f"---\nname: {name}\ntype: user\ndescription: {desc}\n---\n\nTest body.\n",
        encoding="utf-8",
    )


def _build_loop(
    tmp_path: Path,
    *,
    main_responses: list,
    selector_responses: list,
) -> AgentLoop:
    """Wire a minimal AgentLoop for injection tests."""
    memory_dir = tmp_path / "memory"
    project_memory = ProjectMemory(str(memory_dir))

    provider = MockProvider(main_responses, selector_responses=selector_responses)
    transcript = Transcript()
    registry = build_default_registry(tmp_path, transcript=transcript)
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=10_000, reserved_output_tokens=512)
    builder = ContextBuilder(budget=budget, project_memory=project_memory)

    return AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
        project_memory=project_memory,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAttachmentMessagesInjected:
    def test_attachment_messages_injected_before_provider_call(
        self, tmp_path: Path
    ) -> None:
        memory_dir = tmp_path / "memory"
        _write_memory(memory_dir, "user/role", name="User role", desc="coding role")

        loop = _build_loop(
            tmp_path,
            main_responses=[MockProvider.direct_answer("Done")],
            selector_responses=[{"filenames": ["user/role.md"]}],
        )
        loop.run("fix the coding bug please")

        # Transcript should contain at least one ATTACHMENT_MEMORY message
        messages = loop._transcript.all_messages()
        attachment_msgs = [
            m for m in messages if m.type == MessageType.ATTACHMENT_MEMORY
        ]
        assert len(attachment_msgs) >= 1

    def test_attachment_content_contains_system_reminder(
        self, tmp_path: Path
    ) -> None:
        memory_dir = tmp_path / "memory"
        _write_memory(memory_dir, "user/role", name="User role", desc="coding role")

        loop = _build_loop(
            tmp_path,
            main_responses=[MockProvider.direct_answer("Done")],
            selector_responses=[{"filenames": ["user/role.md"]}],
        )
        loop.run("fix the coding bug please")

        messages = loop._transcript.all_messages()
        attachment_msgs = [
            m for m in messages if m.type == MessageType.ATTACHMENT_MEMORY
        ]
        assert len(attachment_msgs) >= 1
        # Content should be wrapped in <system-reminder> tags
        assert "<system-reminder>" in str(attachment_msgs[0].content)
        assert "</system-reminder>" in str(attachment_msgs[0].content)


class TestAlreadySurfacedDeduplication:
    def test_already_surfaced_deduplication(self, tmp_path: Path) -> None:
        memory_dir = tmp_path / "memory"
        _write_memory(memory_dir, "user/role", name="User role", desc="coding role")

        # First run: selector responds with the memory
        # Second run: same query, same selector response
        loop = _build_loop(
            tmp_path,
            main_responses=[
                MockProvider.direct_answer("Done turn 1"),
                MockProvider.direct_answer("Done turn 2"),
            ],
            selector_responses=[
                {"filenames": ["user/role.md"]},
                {"filenames": ["user/role.md"]},  # same response second time
            ],
        )

        # First run: injection happens
        loop.run("fix the coding bug please")
        after_first = sum(
            1 for m in loop._transcript.all_messages()
            if m.type == MessageType.ATTACHMENT_MEMORY
        )

        # Second run: same file already surfaced — should NOT re-inject
        loop.run("fix another coding bug please")
        after_second = sum(
            1 for m in loop._transcript.all_messages()
            if m.type == MessageType.ATTACHMENT_MEMORY
        )

        # Second run should not add new ATTACHMENT_MEMORY messages for the
        # same file (deduplication via already_surfaced)
        assert after_second == after_first


class TestSessionBytesAccumulates:
    def test_session_bytes_accumulates(self, tmp_path: Path) -> None:
        memory_dir = tmp_path / "memory"
        _write_memory(memory_dir, "mem_a", name="Memory A", desc="memory about A")
        _write_memory(memory_dir, "mem_b", name="Memory B", desc="memory about B")

        loop = _build_loop(
            tmp_path,
            main_responses=[MockProvider.direct_answer("Done")],
            selector_responses=[{"filenames": ["mem_a.md"]}],
        )
        assert loop._session_bytes_used == 0

        loop.run("memory about something important")

        # After injection, session_bytes_used should have grown
        assert loop._session_bytes_used > 0

    def test_session_bytes_ceiling_blocks_injection(self, tmp_path: Path) -> None:
        memory_dir = tmp_path / "memory"
        _write_memory(memory_dir, "mem_a", name="Memory A", desc="memory about A")

        loop = _build_loop(
            tmp_path,
            main_responses=[MockProvider.direct_answer("Done")],
            selector_responses=[{"filenames": ["mem_a.md"]}],
        )
        # Pre-fill session bytes over ceiling
        loop._session_bytes_used = 61 * 1024

        loop.run("memory about something important")

        messages = loop._transcript.all_messages()
        attachment_msgs = [
            m for m in messages if m.type == MessageType.ATTACHMENT_MEMORY
        ]
        # No injection because ceiling exceeded
        assert len(attachment_msgs) == 0
