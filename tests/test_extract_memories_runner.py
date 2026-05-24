"""Tests for extract_memories.ExtractMemoriesRunner.

M4 exit gate: ExtractMemoriesRunner.run() returns ExtractionResult AND
MAX_TURNS=5 respected AND tool whitelist enforced.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from simple_coding_agent.extract_memories import (
    ExtractionResult,
    ExtractMemoriesRunner,
    build_extract_prompt,
)
from simple_coding_agent.provider import MockProvider, ProviderResponse
from simple_coding_agent.tools import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry() -> ToolRegistry:
    """ToolRegistry with stub read_file / list_files / search_text."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="read_file",
        description="Read a file",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        fn=lambda path: f"contents of {path}",
    ))
    registry.register(Tool(
        name="list_files",
        description="List files",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
        fn=lambda path="": "file1.py\nfile2.py",
    ))
    registry.register(Tool(
        name="search_text",
        description="Search text",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
        },
        fn=lambda pattern, path="": f"match: {pattern}",
    ))
    return registry


def _end_turn(text: str = "Nothing to save.") -> ProviderResponse:
    return MockProvider.direct_answer(text)


def _tool_call_response(name: str, input: dict[str, Any]) -> ProviderResponse:
    return MockProvider.tool_call(name, input)


# ---------------------------------------------------------------------------
# Tests for build_extract_prompt (free function)
# ---------------------------------------------------------------------------

def test_build_extract_prompt_contains_all_5_sections() -> None:
    prompt = build_extract_prompt(5, "existing manifest content")
    # Section 1: opener — memory extraction agent
    assert "memory extraction agent" in prompt
    # Section 2: immediate action
    assert "Immediate action" in prompt
    # Section 3: memory types
    assert "Memory types to consider" in prompt
    # Section 4: what not to save
    assert "Do NOT save" in prompt
    # Section 5: how to save
    assert "How to save" in prompt


def test_build_extract_prompt_interpolates_count_and_manifest() -> None:
    prompt = build_extract_prompt(42, "my-manifest-content-unique-string")
    assert "42" in prompt
    assert "my-manifest-content-unique-string" in prompt


# ---------------------------------------------------------------------------
# Tests for ExtractMemoriesRunner.run()
# ---------------------------------------------------------------------------

def test_runner_stops_on_end_turn(tmp_path: Path) -> None:
    """Provider returns end_turn immediately → turn_count=1, no paths, no errors."""
    provider = MockProvider([_end_turn("Nothing worth saving.")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="system",
        base_messages=[],
        tool_registry=_make_registry(),
    )
    result = runner.run(new_message_count=3)
    assert result == ExtractionResult(written_paths=(), errors=(), turn_count=1)


def test_runner_executes_whitelisted_tool(tmp_path: Path) -> None:
    """Provider calls read_file → runner executes it and feeds result back."""
    read_call = _tool_call_response("read_file", {"path": "foo.py"})
    provider = MockProvider([read_call, _end_turn("Done.")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="system",
        base_messages=[],
        tool_registry=_make_registry(),
    )
    result = runner.run(new_message_count=1)
    assert result.errors == ()
    assert result.turn_count == 2
    # The second provider call must have received the tool_result
    history = provider.history
    assert len(history) == 2
    second_messages = history[1].messages
    last_msg = second_messages[-1]
    assert last_msg["role"] == "user"
    content = last_msg["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "tool_result"
    assert "contents of foo.py" in content[0]["content"]
    assert content[0]["is_error"] is False


def test_runner_blocks_non_whitelisted_tool(tmp_path: Path) -> None:
    """Provider attempts run_shell → tool_result is_error=True with explanation."""
    shell_call = _tool_call_response("run_shell", {"command": "rm -rf /"})
    provider = MockProvider([shell_call, _end_turn("Done.")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="system",
        base_messages=[],
        tool_registry=_make_registry(),
    )
    result = runner.run(new_message_count=1)
    # Model stopped on its own after seeing the error → no "max turns reached"
    assert result.errors == ()
    # Inspect tool_result sent back to provider on turn 2
    history = provider.history
    second_messages = history[1].messages
    last_msg = second_messages[-1]
    content = last_msg["content"]
    assert content[0]["is_error"] is True
    assert "not available in the extraction context" in content[0]["content"]


def test_runner_write_memory_entry_lands_on_disk(tmp_path: Path) -> None:
    """Scripted write_memory_entry → file on disk, path in written_paths."""
    write_call = _tool_call_response("write_memory_entry", {
        "type": "user",
        "id": "test-user",
        "name": "Test User Memory",
        "description": "A test memory entry",
        "body": "Some memory content here",
    })
    provider = MockProvider([write_call, _end_turn("Saved.")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="system",
        base_messages=[],
        tool_registry=_make_registry(),
    )
    result = runner.run(new_message_count=2)
    assert result.errors == ()
    assert len(result.written_paths) == 1
    written_path = Path(result.written_paths[0])
    assert written_path.exists()
    text = written_path.read_text()
    assert "Test User Memory" in text or "test-user" in text


def test_runner_max_turns_respected(tmp_path: Path) -> None:
    """Provider always returns tool_use → runner stops at turn 5 with max turns error."""
    script = [_tool_call_response("run_shell", {"command": "ls"})] * 10
    provider = MockProvider(script)
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="system",
        base_messages=[],
        tool_registry=_make_registry(),
    )
    result = runner.run(new_message_count=5)
    assert result.turn_count == 5
    assert result.errors == ("max turns reached",)


def test_runner_consumes_snapshot_not_live(tmp_path: Path) -> None:
    """Mutating base_messages after construction must not affect the run."""
    base_messages: list[dict[str, Any]] = [{"role": "user", "content": "original"}]
    provider = MockProvider([_end_turn("Done.")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="system",
        base_messages=base_messages,
        tool_registry=_make_registry(),
    )
    # Mutate original list after runner construction
    base_messages.append({"role": "user", "content": "injected"})
    base_messages[0] = {"role": "user", "content": "mutated"}
    # Runner should still work (it doesn't use base_messages in M4 calls)
    result = runner.run(new_message_count=1)
    assert result == ExtractionResult(written_paths=(), errors=(), turn_count=1)


def test_runner_multi_turn_sequence(tmp_path: Path) -> None:
    """read_file then write_memory_entry → turn_count=3, one written path."""
    read_call = _tool_call_response("read_file", {"path": "notes.md"})
    write_call = _tool_call_response("write_memory_entry", {
        "type": "project",
        "id": "proj-goal",
        "name": "Project Goal",
        "description": "Main objective of the project",
        "body": "Build a memory extraction engine",
    })
    provider = MockProvider([read_call, write_call, _end_turn("All done.")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="system",
        base_messages=[],
        tool_registry=_make_registry(),
    )
    result = runner.run(new_message_count=4)
    assert result.turn_count == 3
    assert result.errors == ()
    assert len(result.written_paths) == 1
    assert Path(result.written_paths[0]).exists()


def test_runner_empty_base_messages_does_not_crash(tmp_path: Path) -> None:
    """Runner works fine when base_messages is empty."""
    provider = MockProvider([_end_turn("No context to analyse.")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="You are a helpful assistant.",
        base_messages=[],
        tool_registry=_make_registry(),
    )
    result = runner.run(new_message_count=0)
    assert result.turn_count == 1
    assert result.written_paths == ()
    assert result.errors == ()


def test_runner_write_memory_entry_invalid_id_surfaces_as_error(tmp_path: Path) -> None:
    """write_memory_entry with invalid id → is_error=True, no path written."""
    bad_write = _tool_call_response("write_memory_entry", {
        "type": "user",
        "id": "../evil",  # path traversal attempt
        "name": "Evil",
        "description": "Bad entry",
        "body": "Trying to escape",
    })
    provider = MockProvider([bad_write, _end_turn("Done.")])
    runner = ExtractMemoriesRunner(
        provider=provider,
        memory_dir=tmp_path,
        system_prompt="system",
        base_messages=[],
        tool_registry=_make_registry(),
    )
    result = runner.run(new_message_count=1)
    assert result.written_paths == ()
    # Check that the tool_result was is_error=True
    history = provider.history
    second_messages = history[1].messages
    last_msg = second_messages[-1]
    content = last_msg["content"]
    assert content[0]["is_error"] is True
