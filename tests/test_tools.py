"""Phase 3: Tool system tests — written before implementation (TDD)."""

import pytest

from simple_coding_agent.tools import (
    Tool,
    ToolExecutor,
    ToolRegistry,
    UnknownToolError,
    preview_result,
)

# --- preview_result ---

def test_preview_short_content_unchanged() -> None:
    assert preview_result("hello", limit=2000) == "hello"


def test_preview_truncates_long_content() -> None:
    content = "x" * 3000
    result = preview_result(content, limit=2000)
    assert len(result) < len(content)
    assert "[truncated" in result
    assert "more chars]" in result


def test_preview_exactly_at_limit() -> None:
    content = "a" * 2000
    assert preview_result(content, limit=2000) == content


def test_preview_one_over_limit() -> None:
    content = "a" * 2001
    result = preview_result(content, limit=2000)
    assert result != content
    assert "[truncated" in result


def test_preview_empty_string() -> None:
    assert preview_result("", limit=2000) == ""


# --- Tool dataclass ---

def test_tool_creation() -> None:
    def echo(text: str) -> str:
        return text

    t = Tool(
        name="echo",
        description="Echoes text",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        fn=echo,
    )
    assert t.name == "echo"
    assert t.description == "Echoes text"
    assert t.max_result_chars == 50_000


def test_tool_custom_max_result_chars() -> None:
    t = Tool(
        name="big",
        description="Big output tool",
        input_schema={},
        fn=lambda: "",
        max_result_chars=100,
    )
    assert t.max_result_chars == 100


def test_tool_none_max_result_chars() -> None:
    t = Tool(
        name="unlimited",
        description="Never externalizes",
        input_schema={},
        fn=lambda: "",
        max_result_chars=None,
    )
    assert t.max_result_chars is None


# --- ToolRegistry ---

def test_registry_register_and_get() -> None:
    registry = ToolRegistry()
    t = Tool(name="ping", description="Ping", input_schema={}, fn=lambda: "pong")
    registry.register(t)
    assert registry.get("ping") is t


def test_registry_get_unknown_raises() -> None:
    registry = ToolRegistry()
    with pytest.raises(UnknownToolError):
        registry.get("no_such_tool")


def test_registry_all_tools() -> None:
    registry = ToolRegistry()
    t1 = Tool(name="a", description="A", input_schema={}, fn=lambda: "")
    t2 = Tool(name="b", description="B", input_schema={}, fn=lambda: "")
    registry.register(t1)
    registry.register(t2)
    tools = registry.all_tools()
    assert len(tools) == 2


def test_registry_to_api_format() -> None:
    registry = ToolRegistry()
    schema = {"type": "object", "properties": {"path": {"type": "string"}}}
    t = Tool(name="read_file", description="Read a file", input_schema=schema, fn=lambda path: "")
    registry.register(t)
    api = registry.to_api_format()
    assert len(api) == 1
    assert api[0]["name"] == "read_file"
    assert api[0]["description"] == "Read a file"
    assert api[0]["input_schema"] == schema


def test_registry_overwrite_same_name() -> None:
    registry = ToolRegistry()
    t1 = Tool(name="x", description="v1", input_schema={}, fn=lambda: "v1")
    t2 = Tool(name="x", description="v2", input_schema={}, fn=lambda: "v2")
    registry.register(t1)
    registry.register(t2)
    assert registry.get("x").description == "v2"


# --- ToolExecutor ---

def test_executor_calls_tool() -> None:
    registry = ToolRegistry()
    registry.register(Tool(
        name="add",
        description="Add numbers",
        input_schema={},
        fn=lambda a, b: str(a + b),
    ))
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("add", {"a": 1, "b": 2})
    assert content == "3"
    assert not is_error


def test_executor_unknown_tool_raises() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    with pytest.raises(UnknownToolError):
        executor.execute("nonexistent", {})


def test_executor_tool_exception_returns_error() -> None:
    def bad_fn(**kwargs: object) -> str:
        raise ValueError("something went wrong")

    registry = ToolRegistry()
    registry.register(Tool(name="bad", description="Bad", input_schema={}, fn=bad_fn))
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("bad", {})
    assert is_error
    assert "something went wrong" in content


def test_executor_returns_string_result() -> None:
    registry = ToolRegistry()
    registry.register(Tool(
        name="hello",
        description="Says hello",
        input_schema={},
        fn=lambda name: f"Hello, {name}!",
    ))
    executor = ToolExecutor(registry)
    content, is_error = executor.execute("hello", {"name": "world"})
    assert content == "Hello, world!"
    assert not is_error
