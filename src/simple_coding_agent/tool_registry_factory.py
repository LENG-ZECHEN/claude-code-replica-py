"""
Phase 9: Factory that wires the safe coding tools into a ToolRegistry.

``build_default_registry(workspace)`` returns a ``ToolRegistry`` with five
tools (``list_files``, ``read_file``, ``write_file``, ``search_text``,
``run_shell``). Each tool is a thin lambda that pre-binds the workspace root
and forwards kwargs to the matching function in ``coding_tools``. All real
behavior (workspace boundary enforcement, secret-file refusal, shell-command
allowlist) lives in ``coding_tools`` -- this module only adapts shapes so
the existing ``AgentLoop`` can drive them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .coding_tools import (
    SearchMatch,
    ShellMode,
    list_files,
    read_file,
    run_shell,
    search_text,
    write_file,
)
from .tools import Tool, ToolRegistry


def _format_search_results(matches: list[SearchMatch]) -> str:
    """Render SearchMatch list as a grep-style block for a tool result."""
    if not matches:
        return "(no matches)"
    return "\n".join(f"{m.path}:{m.line_no}: {m.preview}" for m in matches)


def build_default_registry(
    workspace: str | Path,
    *,
    shell_mode: ShellMode = ShellMode.MOCK,
) -> ToolRegistry:
    """Register the safe coding tools against *workspace* and return the registry.

    Each tool's ``fn`` accepts the same keyword arguments the LLM will send
    via ``ToolExecutor.execute(name, input)`` (which calls ``fn(**input)``).
    Workspace is closed over so the LLM never sees or controls the root.

    ``shell_mode`` selects the execution mode for the ``run_shell`` tool;
    ``ShellMode.MOCK`` (the default) returns deterministic stub output
    without executing anything. ``ShellMode.ALLOWLIST`` runs the command
    through ``subprocess.run`` against the five-command allowlist
    (``pwd``, ``ls``, ``cat``, ``grep``, ``python -m pytest``).
    """
    ws = Path(workspace)
    registry = ToolRegistry()

    list_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "subdir": {
                "type": "string",
                "description": "Optional subdirectory inside the workspace.",
            },
        },
    }
    registry.register(Tool(
        name="list_files",
        description=(
            "List files in the workspace as POSIX relative paths. "
            "Skips secret-like files."
        ),
        input_schema=list_schema,
        fn=lambda subdir=None: "\n".join(list_files(ws, subdir=subdir)),
    ))

    read_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative path to read.",
            },
        },
        "required": ["path"],
    }
    registry.register(Tool(
        name="read_file",
        description="Read a UTF-8 text file inside the workspace.",
        input_schema=read_schema,
        fn=lambda path: read_file(ws, path),
    ))

    write_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative path to write.",
            },
            "content": {
                "type": "string",
                "description": "Text content to write (UTF-8).",
            },
        },
        "required": ["path", "content"],
    }
    registry.register(Tool(
        name="write_file",
        description=(
            "Write text content to a file inside the workspace. "
            "Creates parent directories as needed."
        ),
        input_schema=write_schema,
        fn=lambda path, content: write_file(ws, path, content),
    ))

    search_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Substring to search for (plain text, not regex).",
            },
            "subdir": {
                "type": "string",
                "description": "Optional subdirectory to restrict the search.",
            },
        },
        "required": ["pattern"],
    }
    registry.register(Tool(
        name="search_text",
        description=(
            "Substring search across workspace text files. "
            "Skips secret-like and binary files."
        ),
        input_schema=search_schema,
        fn=lambda pattern, subdir=None: _format_search_results(
            search_text(ws, pattern, subdir=subdir)
        ),
    ))

    run_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Allowlisted command (pwd, ls, cat, grep, python -m pytest). "
                    "Runs in the configured shell mode (MOCK or ALLOWLIST)."
                ),
            },
        },
        "required": ["command"],
    }
    registry.register(Tool(
        name="run_shell",
        description=(
            "Run a safe shell command. Only allowlisted commands pass; "
            "metacharacters and secret paths are refused. Execution mode "
            "is configured at registry build time (default: MOCK)."
        ),
        input_schema=run_schema,
        # ``_mode=shell_mode`` / ``_cwd=ws`` capture the configured mode
        # and workspace root into the lambda's default-arg slots at
        # definition time, avoiding the classic late-binding closure
        # trap. ``cwd`` is required by ``ShellMode.ALLOWLIST`` and is
        # harmlessly passed for ``MOCK`` (which never inspects it).
        fn=lambda command, _mode=shell_mode, _cwd=ws: run_shell(
            command, mode=_mode, cwd=_cwd,
        ),
    ))

    return registry


__all__ = ["build_default_registry"]
