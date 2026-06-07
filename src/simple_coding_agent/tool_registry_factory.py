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
from .plan_mode_tools import register_enter_plan_mode_tool, register_exit_plan_mode_tool
from .snip_tool_model import register_snip_history_tool
from .tools import Tool, ToolRegistry
from .transcript import Transcript


def _format_search_results(matches: list[SearchMatch]) -> str:
    """Render SearchMatch list as a grep-style block for a tool result."""
    if not matches:
        return "(no matches)"
    return "\n".join(f"{m.path}:{m.line_no}: {m.preview}" for m in matches)


def build_default_registry(
    workspace: str | Path,
    *,
    shell_mode: ShellMode = ShellMode.MOCK,
    transcript: Transcript | None = None,
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
        read_only=True,
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
        read_only=True,
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
        read_only=True,
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

    # M4: the model-driven snip_history tool. It captures a live Transcript by
    # closure so the model can delete past tool_result messages by uuid. When
    # no transcript is supplied a fresh one is used (the tool is still
    # registered but acts on empty history); REPL call sites pass the SAME
    # Transcript the AgentLoop holds so model snips reach the live session.
    register_snip_history_tool(registry, transcript if transcript is not None else Transcript())

    # M2: enter_plan_mode tool (plan-surface). Registered unconditionally so
    # the model can always enter plan mode regardless of CLI flags. The
    # mode_setter closure will be replaced when AgentLoop wires the real setter;
    # this default (no-op) satisfies tool-registry unit tests that build the
    # registry without a loop.
    register_enter_plan_mode_tool(registry, lambda _mode: None)

    # M3: exit_plan_mode tool (plan-surface). The no-op mode_setter and
    # always-False approval_callback are replaced by AgentLoop._register_tools
    # with the real _set_permission_mode and _exit_plan_mode_callback / the CLI's
    # _confirm_exit_plan helper. The defaults keep unit tests that build the
    # registry directly from needing a real loop or CLI.
    register_exit_plan_mode_tool(registry, lambda _mode: None, lambda _plan: False)

    return registry


__all__ = ["build_default_registry"]
