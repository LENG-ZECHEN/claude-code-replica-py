"""
Phase 10 / P9-M1: Runnable CLI for simple_coding_agent.

Two modes:

  ``simple-agent``                  -- one-shot MockProvider demo (the
                                       original Phase 10 behavior).
  ``simple-agent --repl``           -- multi-turn interactive REPL with a
                                       shared AgentLoop, MockProvider for
                                       determinism, and slash commands
                                       (``/exit``, ``/quit``, ``/help``).
  ``simple-agent memory ...``       -- delegate to memory_cli.

Long-running modes (``--repl``) are what makes the P1-P8 context-management
mechanisms actually reachable: snip, full-compact, microcompact, reactive
compact, and prompt-cache stability all require more than one provider call
to fire. The one-shot mode is preserved for backwards-compatible smoke
tests; argparse routes between them based on flags / positional args.

This module does no network I/O and requires no API key. All flags map
into either ``AgentLoop`` constructor arguments or ``ContextBudget`` fields.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# Importing readline upgrades the built-in input() to a proper line editor:
# backspace/delete redraw correctly past terminal width (fixes long-line
# deletion lag), arrow-key history works, and unbound escape sequences from
# mouse-wheel events are swallowed instead of echoed as garbage. Inert when
# stdin is not a TTY, so test monkeypatches over sys.stdin are unaffected.
try:
    import readline  # noqa: F401
except ImportError:
    pass

from .auto_learn import detect_cue, format_hint
from .claude_md import ClaudeMdLoader
from .coding_tools import ShellMode
from .compact import ContextCompactor, MicroCompactor
from .context import ContextBudget, ContextBuilder
from .loop import AgentLoop, LoopStatus
from .memory import (
    MemoryEntry,
    MemoryType,
    ProjectMemory,
    SessionMemory,
    _check_body_for_secrets,
)
from .metrics import MetricsCollector
from .models import ToolCall
from .permission import PermissionMode
from .plan_mode_tools import register_exit_plan_mode_tool
from .provider import MockProvider, Provider, ProviderResponse
from .session_store import (
    InvalidSessionNameError,
    SessionNotFoundError,
    load_session,
    save_session,
    session_path_for,
)
from .snip import SnipTool
from .todo import TodoItem
from .todo_tool import register_todo_write_tool
from .tool_registry_factory import build_default_registry
from .tool_result_store import ToolResultStore
from .tools import ToolExecutor
from .trace import NullTracer, StderrTracer, Tracer
from .transcript import Transcript

_SESSION_MEMORY_FILENAME = "session_memory.json"
_SIMPLE_AGENT_DIR = ".simple-agent"
_MEMORY_SUBDIR = "memory"
_VALID_MEMORY_TYPES = tuple(t.value for t in MemoryType)
_PROJECT_MEMORY_ENV_VAR = "SIMPLE_AGENT_MEMORY_DIR"

# ---------------------------------------------------------------------------
# Demo-mode constants (preserved from Phase 10)
# ---------------------------------------------------------------------------

_USER_INPUT: str = (
    "Read src/app.py, find where 'hello' appears, "
    "and write a short REPORT.md summary."
)

_REPORT_BODY: str = (
    "# Demo report\n\n"
    "- Read src/app.py\n"
    "- Found 'hello' on the greet() return line\n"
    "- This file was written by simple-agent via MockProvider\n"
)

_FINAL_ANSWER: str = (
    "I read src/app.py, located the 'hello' substring on the greet() "
    "return line, and wrote a summary to REPORT.md."
)

_PREVIEW_CHARS: int = 200

# ---------------------------------------------------------------------------
# REPL constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_STEPS: int = 10
_DEFAULT_SNIP_NUDGE_GROWTH_TOKENS: int = 10_000
_DEFAULT_CONTEXT_TOKENS: int = 200_000
_DEFAULT_RESERVED_OUTPUT_TOKENS: int = 8_192
# M1 (ctx-pdf): built-in defaults for the four PDF-threshold flags. These
# mirror the compact.py constructor defaults; they have no _AGGRESSIVE_THRESHOLDS
# preset entry, so (like --max-steps) they resolve to explicit-flag-or-default.
_DEFAULT_MICROCOMPACT_KEEP_RECENT: int = 5
_DEFAULT_MICROCOMPACT_MINUTES: int = 60
_DEFAULT_OUTPUT_HEADROOM: int = 12_000
_DEFAULT_COMPACT_HEADROOM: int = 20_000
_DEFAULT_MIN_SESSION_TOKENS: int = 30_000
_REPL_BANNER: str = (
    "simple-agent REPL -- type /help for commands, /exit to quit.\n"
    "MockProvider only: no network, no API key, no real shell.\n"
)
_REPL_PROMPT: str = "> "
_REPL_HELP_TEXT: str = (
    "Commands:\n"
    "  /help                          Show this help.\n"
    "  /stats                         Show per-mechanism counters for this session.\n"
    "  /save <name>                   Persist transcript + last summary to a named session.\n"
    "  /load <name>                   Restore a previously saved session into this REPL.\n"
    "  /remember <type> <id> <body>   Save a project memory entry (auto-learn target).\n"
    "  /remember-session <text>       Add a session-scoped memory note "
    "(lost when REPL ends unless saved).\n"
    "  /todos                         Show the current todo list.\n"
    "  /plan                          Toggle plan mode (silently; bidirectional). "
    "Writes are soft-rejected while in plan mode.\n"
    "  /exit, /quit                   Leave the REPL.\n"
)
_REPL_DEFAULT_ANSWER: str = (
    "[MockProvider] Acknowledged. (No real LLM is wired in this build.)"
)

# ---------------------------------------------------------------------------
# Aggressive-thresholds preset (M2). Single switch (``--aggressive-thresholds``)
# that lowers every relevant threshold to demo-friendly values so the context-
# management mechanisms (compact / microcompact / snip / externalize) actually
# fire in a short interactive session. Imported by ``visibility_full_demo.py``
# (M3); the key set is frozen.
# ---------------------------------------------------------------------------

_AGGRESSIVE_THRESHOLDS: dict[str, int | float] = {
    "compact_threshold": 0.2,
    "keep_recent": 2,
    "microcompact_minutes": 1,
    "max_inline_chars": 2_000,
    "total_budget_chars": 8_000,
    "snip_keep_recent": 1,
    "context_tokens": 4_000,
    "reserved_output_tokens": 512,
}

_AGGRESSIVE_BANNER: str = (
    "[aggressive-thresholds] compact={compact_threshold}, "
    "microcompact={microcompact_minutes}min, "
    "inline={max_inline_chars_k}k, total={total_budget_chars_k}k, "
    "snip_keep={snip_keep_recent}, ctx={context_tokens_k}k, "
    "out={reserved_output_tokens}"
)


def _resolve_threshold(
    explicit: int | None,
    preset_key: str | None,
    default: int,
    *,
    aggressive: bool,
) -> int:
    """Resolve one CLI-tunable threshold via three-state precedence.

    Precedence (highest first):
      1. an explicit user flag (any value, even 0) always wins;
      2. otherwise, when ``--aggressive-thresholds`` is active and the
         field has a preset entry, the preset value applies;
      3. otherwise the built-in default applies.

    ``preset_key=None`` marks a field with no entry in
    ``_AGGRESSIVE_THRESHOLDS`` (e.g. ``--max-steps``), so such a field
    falls straight through to ``default`` when no explicit value is given.

    This is the single source of truth for the precedence rule. Both
    ``_run_repl`` (MockProvider) and ``openai_cli._run_openai_repl`` reach
    it through ``_build_repl_loop``, so the two REPLs cannot drift.
    """
    if explicit is not None:
        return explicit
    if aggressive and preset_key is not None:
        return int(_AGGRESSIVE_THRESHOLDS[preset_key])
    return default


def _format_aggressive_banner() -> str:
    """Render the one-line banner from ``_AGGRESSIVE_THRESHOLDS`` values."""
    return _AGGRESSIVE_BANNER.format(
        compact_threshold=_AGGRESSIVE_THRESHOLDS["compact_threshold"],
        microcompact_minutes=_AGGRESSIVE_THRESHOLDS["microcompact_minutes"],
        max_inline_chars_k=int(_AGGRESSIVE_THRESHOLDS["max_inline_chars"]) // 1_000,
        total_budget_chars_k=int(_AGGRESSIVE_THRESHOLDS["total_budget_chars"]) // 1_000,
        snip_keep_recent=_AGGRESSIVE_THRESHOLDS["snip_keep_recent"],
        context_tokens_k=int(_AGGRESSIVE_THRESHOLDS["context_tokens"]) // 1_000,
        reserved_output_tokens=_AGGRESSIVE_THRESHOLDS["reserved_output_tokens"],
    )


# Test hooks: REPL records the AgentLoop instances it created so tests can
# inspect token budget / max_steps without monkeypatching constructors.
_LAST_LOOPS: list[AgentLoop] = []


# ---------------------------------------------------------------------------
# Demo-mode helpers (Phase 10 logic, unchanged)
# ---------------------------------------------------------------------------

def _seed_workspace(ws: Path) -> None:
    """Seed the temporary workspace with the file the script expects to read."""
    (ws / "src").mkdir()
    (ws / "src" / "app.py").write_text(
        "def greet(name):\n    return f'hello, {name}'\n",
        encoding="utf-8",
    )


def _script() -> list[ProviderResponse]:
    """Deterministic MockProvider script: read -> search -> write -> answer."""
    return [
        MockProvider.tool_call(
            "read_file", {"path": "src/app.py"}, id="tu_read"
        ),
        MockProvider.tool_call(
            "search_text", {"pattern": "hello"}, id="tu_search"
        ),
        MockProvider.tool_call(
            "write_file",
            {"path": "REPORT.md", "content": _REPORT_BODY},
            id="tu_write",
        ),
        MockProvider.direct_answer(_FINAL_ANSWER),
    ]


def _truncate(text: str, limit: int = _PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [+{len(text) - limit} more chars]"


def _format_call(call: ToolCall) -> str:
    kvs = ", ".join(f"{k}={_truncate(str(v), 60)!r}" for k, v in call.input.items())
    return f"{call.name}({kvs})"


def _run_demo(workspace: Path, *, shell_mode: ShellMode = ShellMode.MOCK) -> int:
    """Wire components, run the loop, print a structured trace, return exit code."""
    _seed_workspace(workspace)
    transcript = Transcript()
    registry = build_default_registry(
        workspace, shell_mode=shell_mode, transcript=transcript
    )
    executor = ToolExecutor(registry)
    budget = ContextBudget(max_tokens=200_000, reserved_output_tokens=8_192)
    builder = ContextBuilder(
        budget=budget,
        workspace_path=workspace,
        claude_md_loader=ClaudeMdLoader(),
    )
    provider = MockProvider(_script())
    loop = AgentLoop(
        provider=provider,
        tool_executor=executor,
        transcript=transcript,
        context_builder=builder,
        budget=budget,
        registry=registry,
    )

    print("=" * 60)
    print("simple_coding_agent -- MockProvider demo (Phase 10)")
    print("=" * 60)
    print(f"Workspace:   {workspace}")
    print(f"User input:  {_USER_INPUT}")
    print()

    result = loop.run(_USER_INPUT)

    for step in result.steps:
        print(f"--- Turn {step.turn} ---")
        if step.tool_calls:
            for call, res in zip(step.tool_calls, step.tool_results, strict=True):
                print(f"Tool call:   {_format_call(call)}")
                marker = "ERROR" if res.is_error else "Result"
                print(f"{marker}:      {_truncate(res.content)}")
        else:
            print(f"Final text:  {step.assistant_message.content}")
        print()

    print("--- Final answer ---")
    print(result.answer or "(no answer)")
    print()
    print(f"Loop status: {result.status}")
    report = workspace / "REPORT.md"
    print(f"Generated:   {report} (exists={report.exists()})")
    print()
    print(
        "Notes: MockProvider only -- no LLM call, no API key required. "
        "All file ops were confined to the temporary workspace."
    )
    print(
        "Gates: pytest, mypy, and ruff are expected to remain green after Phase 10."
    )

    return 0 if result.status == LoopStatus.COMPLETED else 1


# ---------------------------------------------------------------------------
# REPL implementation
# ---------------------------------------------------------------------------

def _make_repl_provider(_workspace: Path) -> MockProvider:
    """Provider used by the REPL by default.

    Returns a MockProvider preloaded with a generous pool of canned
    acknowledgements -- enough to survive long sessions without exhausting
    the script. Tests replace this hook with a tighter scripted provider
    via ``monkeypatch.setattr(cli_mod, "_make_repl_provider", ...)``.
    """
    return MockProvider([
        MockProvider.direct_answer(_REPL_DEFAULT_ANSWER) for _ in range(1_000)
    ])


def _session_memory_path(workspace: Path) -> Path:
    """Per-workspace JSON snapshot location for SessionMemory auto-persist."""
    return workspace / _SIMPLE_AGENT_DIR / _SESSION_MEMORY_FILENAME


def _resolve_memory_dir(workspace: Path) -> Path:
    """Resolve the ProjectMemory storage directory for a REPL session.

    Precedence: ``SIMPLE_AGENT_MEMORY_DIR`` env var (absolute path) >
    ``<workspace>/.simple-agent/memory/``. Mirrors ``memory_cli`` but
    anchors the workspace-relative fallback to the REPL's workspace
    (not ``Path.cwd()``) so tests with isolated workspaces stay isolated.
    """
    raw = os.environ.get(_PROJECT_MEMORY_ENV_VAR)
    if raw:
        return Path(raw).expanduser().resolve()
    return (workspace / _SIMPLE_AGENT_DIR / _MEMORY_SUBDIR).resolve()


def _open_project_memory(
    workspace: Path,
    *,
    tracer: Tracer | None = None,
) -> ProjectMemory:
    """Build a ProjectMemory rooted at the resolved storage dir.

    ``ProjectMemory`` already calls ``os.makedirs(..., exist_ok=True)``
    so we do not need to create the directory ourselves here.
    """
    storage = _resolve_memory_dir(workspace)
    storage.mkdir(parents=True, exist_ok=True)
    return ProjectMemory(storage_dir=str(storage), tracer=tracer)


def _build_repl_loop(
    workspace: Path,
    *,
    max_steps: int | None = None,
    max_context_tokens: int | None = None,
    reserved_output_tokens: int | None = None,
    microcompact_keep_recent: int | None = None,
    microcompact_minutes: int | None = None,
    output_headroom: int | None = None,
    compact_headroom: int | None = None,
    min_session_tokens: int | None = None,
    snip_nudge_growth_tokens: int | None = None,
    session_memory: SessionMemory | None = None,
    project_memory: ProjectMemory | None = None,
    provider: Provider | None = None,
    system_prompt: str | None = None,
    shell_mode: ShellMode = ShellMode.MOCK,
    tracer: Tracer | None = None,
    aggressive_thresholds: bool = False,
    extract_memories_enabled: bool = False,
    extract_throttle_n: int = 1,
    session_memory_enabled: bool = False,
    summarizer_mode: str = "auto",
    todo_nudge_enabled: bool = True,
    todo_reminder_turns: int | None = None,
) -> AgentLoop:
    """Wire one shared AgentLoop for the REPL session.

    ``provider`` and ``system_prompt`` are optional injection points so
    ``openai_cli`` can reuse this helper while supplying its own
    ``OpenAIProvider`` (and a coder-style system prompt). When omitted
    the REPL falls back to the MockProvider hook used by the default
    ``simple-agent --repl`` mode.

    The optional ``tracer`` is threaded into every component that owns
    a fire site (``ContextBuilder``, ``ClaudeMdLoader``,
    ``ContextCompactor``, ``MicroCompactor``, ``SnipTool``,
    ``ToolResultStore``, ``ProjectMemory``, ``AgentLoop``) so a single
    ``--verbose`` flag activates trace output across the whole pipeline.
    """
    active_tracer: Tracer = tracer if tracer is not None else NullTracer()
    # Resolve provider EARLY so ContextCompactor can reuse the SAME instance
    # for LLM-based summarization. The kwarg `provider` is non-None only when
    # a real provider (e.g. OpenAIProvider via openai_cli) was injected by
    # the caller; the simple-agent REPL falls back to MockProvider, in which
    # case `summarizer_provider` stays None and ContextCompactor keeps using
    # RuleBasedSummarizer (preserving the no-extra-API-call test contract).
    #
    # `summarizer_mode` lets the operator override the auto-detect:
    #   * "auto" (default) — use real provider when present, else rule-based
    #   * "rule"          — force RuleBasedSummarizer (cost = 0)
    #   * "llm"           — force LLMSummarizer (errors if no real provider)
    resolved_provider = provider if provider is not None else _make_repl_provider(workspace)
    if summarizer_mode not in ("auto", "rule", "llm"):
        raise ValueError(
            f"summarizer_mode must be one of 'auto', 'rule', 'llm'; "
            f"got {summarizer_mode!r}"
        )
    if summarizer_mode == "rule":
        summarizer_provider: Provider | None = None
    elif summarizer_mode == "llm":
        if provider is None:
            raise SystemExit(
                "--summarizer llm requires a real provider (e.g. via "
                "openai-agent with OPENAI_API_KEY or DASHSCOPE_API_KEY set)."
            )
        summarizer_provider = provider
    else:  # "auto"
        summarizer_provider = provider  # None when MockProvider fallback
    # M4: the transcript is created BEFORE the registry so the snip_history
    # tool registered inside build_default_registry closes over the SAME
    # Transcript instance the AgentLoop holds — model snips reach live history.
    transcript = Transcript()
    registry = build_default_registry(
        workspace, shell_mode=shell_mode, transcript=transcript
    )
    executor = ToolExecutor(registry)
    # Three-state precedence (explicit flag > aggressive preset > default)
    # is resolved here, the one place both REPLs share. ``None`` means "no
    # explicit flag"; ``_resolve_threshold`` then falls back to the preset
    # (when active) or the built-in default. ``--max-steps`` has no preset
    # entry, so it resolves to its default unless explicitly set.
    resolved_max_steps = _resolve_threshold(
        max_steps, None, _DEFAULT_MAX_STEPS, aggressive=aggressive_thresholds,
    )
    resolved_context_tokens = _resolve_threshold(
        max_context_tokens, "context_tokens", _DEFAULT_CONTEXT_TOKENS,
        aggressive=aggressive_thresholds,
    )
    resolved_reserved_output_tokens = _resolve_threshold(
        reserved_output_tokens, "reserved_output_tokens",
        _DEFAULT_RESERVED_OUTPUT_TOKENS, aggressive=aggressive_thresholds,
    )
    # M1 PDF-threshold flags. preset_key=None (no _AGGRESSIVE_THRESHOLDS entry),
    # so these resolve to explicit-flag-or-default — the --max-steps pattern.
    resolved_microcompact_keep_recent = _resolve_threshold(
        microcompact_keep_recent, None, _DEFAULT_MICROCOMPACT_KEEP_RECENT,
        aggressive=aggressive_thresholds,
    )
    resolved_microcompact_minutes = _resolve_threshold(
        microcompact_minutes, "microcompact_minutes", _DEFAULT_MICROCOMPACT_MINUTES,
        aggressive=aggressive_thresholds,
    )
    resolved_output_headroom = _resolve_threshold(
        output_headroom, None, _DEFAULT_OUTPUT_HEADROOM,
        aggressive=aggressive_thresholds,
    )
    resolved_compact_headroom = _resolve_threshold(
        compact_headroom, None, _DEFAULT_COMPACT_HEADROOM,
        aggressive=aggressive_thresholds,
    )
    resolved_min_session_tokens = _resolve_threshold(
        min_session_tokens, None, _DEFAULT_MIN_SESSION_TOKENS,
        aggressive=aggressive_thresholds,
    )
    # snip-nudge growth threshold. preset_key=None (the --max-steps pattern):
    # it has no _AGGRESSIVE_THRESHOLDS entry because the model-snip nudge is
    # the lighter alternative to a full compact, so it only fires in the
    # no-auto-compaction regime. Drive it with an explicit low value plus a
    # roomy context budget (i.e. WITHOUT --aggressive-thresholds).
    resolved_snip_nudge_growth_tokens = _resolve_threshold(
        snip_nudge_growth_tokens, None, _DEFAULT_SNIP_NUDGE_GROWTH_TOKENS,
        aggressive=aggressive_thresholds,
    )
    # When the aggressive preset is on, swap in low thresholds for the
    # non-flag-backed fields (compact / microcompact / snip / externalize).
    # The flag-backed budget fields above already honour explicit > preset.
    if aggressive_thresholds:
        compact_threshold = float(_AGGRESSIVE_THRESHOLDS["compact_threshold"])
        keep_recent_kept = int(_AGGRESSIVE_THRESHOLDS["keep_recent"])
        max_inline_chars = int(_AGGRESSIVE_THRESHOLDS["max_inline_chars"])
        total_budget_chars = int(_AGGRESSIVE_THRESHOLDS["total_budget_chars"])
        snip_keep_recent = int(_AGGRESSIVE_THRESHOLDS["snip_keep_recent"])
        tool_result_store: ToolResultStore | None = ToolResultStore(
            max_inline_chars=max_inline_chars,
            total_budget_chars=total_budget_chars,
            tracer=active_tracer,
        )
        compactor = ContextCompactor(
            keep_recent=keep_recent_kept,
            compact_threshold=compact_threshold,
            output_headroom=resolved_output_headroom,
            compact_headroom=resolved_compact_headroom,
            min_session_tokens=resolved_min_session_tokens,
            provider=summarizer_provider,
            tracer=active_tracer,
        )
        microcompactor = MicroCompactor(
            threshold_minutes=resolved_microcompact_minutes,
            keep_recent=resolved_microcompact_keep_recent,
            tracer=active_tracer,
        )
        snip_tool = SnipTool(keep_recent=snip_keep_recent, tracer=active_tracer)
    else:
        tool_result_store = None
        compactor = ContextCompactor(
            output_headroom=resolved_output_headroom,
            compact_headroom=resolved_compact_headroom,
            min_session_tokens=resolved_min_session_tokens,
            provider=summarizer_provider,
            tracer=active_tracer,
        )
        microcompactor = MicroCompactor(
            threshold_minutes=resolved_microcompact_minutes,
            keep_recent=resolved_microcompact_keep_recent,
            tracer=active_tracer,
        )
        snip_tool = SnipTool(tracer=active_tracer)

    budget = ContextBudget(
        max_tokens=resolved_context_tokens,
        reserved_output_tokens=resolved_reserved_output_tokens,
    )
    builder = ContextBuilder(
        budget=budget,
        tool_result_store=tool_result_store,
        workspace_path=workspace,
        claude_md_loader=ClaudeMdLoader(tracer=active_tracer),
        project_memory=project_memory,
        enable_todo_teaching=todo_nudge_enabled,
        tracer=active_tracer,
    )
    _todos_shared: list[TodoItem] | None
    if todo_nudge_enabled:
        _todos_list: list[TodoItem] = []
        _todos_shared = _todos_list

        def _get_shared_todos() -> list[TodoItem]:
            return list(_todos_list)

        def _set_shared_todos(todos: list[TodoItem]) -> None:
            _todos_list[:] = todos

        register_todo_write_tool(registry, _get_shared_todos, _set_shared_todos)
    else:
        _todos_shared = None

    loop_kwargs: dict[str, object] = {
        "provider": resolved_provider,
        "tool_executor": executor,
        "transcript": transcript,
        "context_builder": builder,
        "tool_result_store": tool_result_store,
        "budget": budget,
        "registry": registry,
        "compactor": compactor,
        "microcompactor": microcompactor,
        "snip_tool": snip_tool,
        "session_memory": session_memory,
        "project_memory": project_memory,
        "metrics": MetricsCollector(),
        "tracer": active_tracer,
        "max_steps": resolved_max_steps,
        "snip_nudge_growth_tokens": resolved_snip_nudge_growth_tokens,
        "extract_memories_enabled": extract_memories_enabled,
        "extract_throttle_n": extract_throttle_n,
        "session_memory_enabled": session_memory_enabled,
        "todo_nudge_enabled": todo_nudge_enabled,
        **({"todo_reminder_turns": todo_reminder_turns} if todo_reminder_turns is not None else {}),
        **({"todo_state": _todos_shared} if _todos_shared is not None else {}),
    }
    if system_prompt is not None:
        loop_kwargs["system_prompt"] = system_prompt
    loop = AgentLoop(**loop_kwargs)  # type: ignore[arg-type]
    # Re-register exit_plan_mode with the CLI's approval gate, overwriting the
    # no-op _exit_plan_mode_callback wired by AgentLoop._register_tools(). This
    # mirrors the enter_plan_mode re-registration pattern in _register_tools:
    # ToolRegistry.register() silently replaces the prior entry.
    register_exit_plan_mode_tool(
        registry,
        loop._set_permission_mode,
        _confirm_exit_plan,
        metrics=loop._metrics,
    )
    _LAST_LOOPS.append(loop)
    return loop


def _confirm_exit_plan(plan_text: str) -> bool:
    """Block on user approval when the model calls exit_plan_mode.

    Prints the proposed plan, then reads one line from stdin:
      "y" / "Y"                  → approved (returns True)
      "n" / "N" / "" / EOF / ^C → rejected (returns False)

    Source: ExitPlanModeV2Tool.ts approval-gate pattern (the user-confirmation
    prompt shown before the model regains write privileges).
    """
    print("\n--- Proposed plan ---")
    print(plan_text)
    print("---------------------")
    try:
        return input("Approve plan? (y/N): ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def _handle_slash_command(cmd: str, loop: AgentLoop | None = None) -> str:
    """Map a slash command to a control signal.

    Returns:
      ``"exit"``     -- caller should terminate the loop.
      ``"continue"`` -- handled (printed help / stats / hint), keep looping.
    """
    tokens = cmd.strip().split()
    head = tokens[0]
    if head in ("/exit", "/quit"):
        return "exit"
    if head == "/help":
        print(_REPL_HELP_TEXT, end="")
        return "continue"
    if head == "/stats":
        if loop is None:
            print("(no active session)")
        else:
            print(loop._metrics.format_stats())
        return "continue"
    if head == "/save":
        _handle_save_command(tokens[1:], loop)
        return "continue"
    if head == "/load":
        _handle_load_command(tokens[1:], loop)
        return "continue"
    if head == "/remember":
        _handle_remember_command(tokens[1:], loop)
        return "continue"
    if head == "/remember-session":
        _handle_remember_session_command(tokens[1:], loop)
        return "continue"
    if head == "/todos":
        _handle_todos_command(loop)
        return "continue"
    if head == "/plan":
        _handle_plan_command(loop)
        return "continue"
    print(f"Unknown command: {head!r}. Try /help for the command list.")
    return "continue"


def _handle_plan_command(loop: AgentLoop | None) -> None:
    """Implement ``/plan``: bidirectional NORMAL↔PLAN toggle (no approval prompt).

    The user gets a fast manual escape that preserves transcript history so
    they can inherit the read_file/search_text context accumulated during
    planning and continue in NORMAL — or quickly enter plan mode to constrain
    the next model turn. Both transitions emit a 'permission' trace with
    source="slash" for observability.

    Source: TS /plan slash is also bidirectional via the underlying setMode API.
    """
    if loop is None:
        print("Cannot toggle plan mode outside a loop.")
        return
    if loop._permission_mode == PermissionMode.NORMAL:
        loop._set_permission_mode(PermissionMode.PLAN, source="slash")
        print(
            "Plan mode entered. Write tools will be soft-rejected. "
            "Use /plan again to exit, or let the model call ExitPlanMode."
        )
    else:
        loop._set_permission_mode(PermissionMode.NORMAL, source="slash")
        print("Plan mode exited. Write tools re-enabled.")


def _handle_remember_command(args: list[str], loop: AgentLoop | None) -> None:
    """Implement ``/remember <type> <id> <body...>``.

    Saves a ``MemoryEntry`` into the active loop's ``ProjectMemory``,
    surfacing the same secret-rejection and path-traversal guards as
    ``simple-agent memory add``. Bodies span the remainder of the line
    so users can paste multi-word feedback without quoting.
    """
    if loop is None:
        print("(no active session)")
        return
    project_memory = loop._project_memory
    if project_memory is None:
        print("(no project memory configured for this REPL)")
        return
    if len(args) < 3:
        print("Usage: /remember <type> <id> <body...>")
        return
    type_str, entry_id, *body_parts = args
    if type_str not in _VALID_MEMORY_TYPES:
        print(
            f"Unknown memory type: {type_str!r}. "
            f"Valid types: {', '.join(_VALID_MEMORY_TYPES)}."
        )
        return
    entry = MemoryEntry(
        name=entry_id,
        body=" ".join(body_parts),
        type=MemoryType(type_str),
        id=entry_id,
    )
    try:
        project_memory.save(entry)
    except ValueError as err:
        print(f"Could not save memory: {err}")
        return
    print(f"Remembered {entry.id} ({type_str}).")


def _handle_remember_session_command(
    args: list[str], loop: AgentLoop | None
) -> None:
    """Implement ``/remember-session <text...>``.

    Appends an ephemeral session-scoped memory entry to the active loop's
    ``SessionMemory``. The REPL's exit hook persists the session memory
    via ``dump_json``, so the next REPL invocation in the same workspace
    can rehydrate it.

    Secret bodies are rejected via the same filter as ``/remember`` so a
    malicious-but-friendly note like ``Bearer eyJ...`` never lands in
    persisted session memory.
    """
    if loop is None:
        print("(no active session)")
        return
    session_memory = loop._session_memory
    if session_memory is None:
        print("(no session memory configured for this REPL)")
        return
    if not args:
        print("Usage: /remember-session <text...>")
        return
    body = " ".join(args)
    try:
        _check_body_for_secrets(body)
    except ValueError as err:
        print(f"Could not save session memory: {err}")
        return
    entry = MemoryEntry(
        name="session note",
        body=body,
        type=MemoryType.PROJECT,
    )
    session_memory.add(entry)
    print(f"Remembered session note {entry.id[:8]}.")


_TODO_GLYPHS: dict[str, str] = {
    "pending": "☐",
    "in_progress": "▶",
    "completed": "☑",
}


def _handle_todos_command(loop: AgentLoop | None) -> None:
    if loop is None or not loop._todos:
        print("(no todos)")
        return
    for i, todo in enumerate(loop._todos, 1):
        glyph = _TODO_GLYPHS.get(str(todo.status), "?")
        print(f"  {i}. {glyph} {todo.content}")


def _handle_save_command(args: list[str], loop: AgentLoop | None) -> None:
    """Implement ``/save <name>``: persist transcript + summary to disk."""
    if not args:
        print("Usage: /save <name>")
        return
    if loop is None:
        print("(no active session)")
        return
    name = args[0]
    try:
        path = session_path_for(name)
    except InvalidSessionNameError as err:
        print(f"Invalid session name: {err}")
        return
    try:
        save_session(
            path,
            transcript=loop._transcript,
            last_summary=loop._last_summary,
            session_memory_state=loop._session_memory_state,
        )
    except OSError as err:
        print(f"(warning: could not save session {name!r}: {err})")
        return
    print(f"Saved session to {path}")


def _apply_resume(name: str, loop: AgentLoop) -> int:
    """Load the named session into ``loop`` before the REPL reads input.

    Returns 0 on success and 2 on a clear failure (invalid name, missing
    file, schema error). The exit code is intentionally distinct from a
    normal ``/exit`` so harness scripts can distinguish startup failures.
    """
    try:
        path = session_path_for(name)
    except InvalidSessionNameError as err:
        print(f"Invalid session name: {err}")
        return 2
    try:
        transcript, last_summary, sm_state = load_session(path)
    except SessionNotFoundError:
        print(f"No such session: {name!r}")
        return 2
    except (ValueError, OSError) as err:
        print(f"(warning: could not load session {name!r}: {err})")
        return 2
    loop._transcript.replace_all(transcript.all_messages())
    loop._last_summary = last_summary
    loop._session_memory_state = sm_state
    loop._session_memory_cursor = None  # will re-scan from scratch on next update
    # The microcompact bookkeeping tracks a uuid from the previous
    # transcript; after a transcript replacement that pointer is stale,
    # so reset it to allow microcompact to re-evaluate the new transcript.
    loop._microcompacted_against_assistant_uuid = None
    print(f"Resumed session from {path}")
    return 0


def _handle_load_command(args: list[str], loop: AgentLoop | None) -> None:
    """Implement ``/load <name>``: restore transcript + summary in place."""
    if not args:
        print("Usage: /load <name>")
        return
    if loop is None:
        print("(no active session)")
        return
    name = args[0]
    try:
        path = session_path_for(name)
    except InvalidSessionNameError as err:
        print(f"Invalid session name: {err}")
        return
    try:
        transcript, last_summary, sm_state = load_session(path)
    except SessionNotFoundError:
        print(f"No such session: {name!r}")
        return
    except (ValueError, OSError) as err:
        print(f"(warning: could not load session {name!r}: {err})")
        return
    loop._transcript.replace_all(transcript.all_messages())
    loop._last_summary = last_summary
    loop._session_memory_state = sm_state
    loop._session_memory_cursor = None  # will re-scan from scratch on next update
    # The microcompact bookkeeping tracks a uuid from the previous
    # transcript; after a transcript replacement that pointer is stale,
    # so reset it to allow microcompact to re-evaluate the new transcript.
    loop._microcompacted_against_assistant_uuid = None
    print(f"Loaded session from {path}")


def _read_input_line() -> str | None:
    """Read one line from stdin. Return None on EOF.

    Flush stdout/stderr before input() so that all banner/trace output is
    rendered before readline takes the terminal — otherwise the first
    keystroke can race with deferred output and the first line appears to
    be dropped on cold start.
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except (OSError, ValueError):
        pass
    try:
        return input(_REPL_PROMPT)
    except EOFError:
        return None


_STEP_PREVIEW_CHARS: int = 240


def _format_step_preview(text: str, limit: int = _STEP_PREVIEW_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [+{len(text) - limit} more chars]"


def _print_tool_step(call_name: str, call_input: object, result_text: str, is_error: bool) -> None:
    """Render one tool_use+tool_result pair to stderr so it interleaves
    cleanly with both streamed assistant text on stdout and `[trace]` lines."""
    marker = "ERROR" if is_error else "Result"
    print(file=sys.stderr)
    print(f"Tool: {call_name}({call_input})", file=sys.stderr)
    print(f"{marker}: {_format_step_preview(result_text)}", file=sys.stderr)
    print(file=sys.stderr)


def _print_steps_from_result(result: object) -> None:
    """Non-stream path: walk the LoopResult.steps and print each tool pair."""
    for step in getattr(result, "steps", ()) or ():
        if not getattr(step, "tool_calls", None):
            continue
        print(f"--- Turn {step.turn} ---", file=sys.stderr)
        for call, tool_result in zip(step.tool_calls, step.tool_results, strict=True):
            _print_tool_step(
                call.name, call.input, tool_result.content, bool(tool_result.is_error)
            )


def _run_turn(
    loop: AgentLoop, user_input: str, stream: bool, *, show_steps: bool = False
) -> None:
    """Drive one user turn; print the assistant answer.

    When ``show_steps`` is True, also render each tool_use+tool_result pair —
    in stream mode via ``tool_step`` events as they arrive, in non-stream mode
    by walking ``LoopResult.steps`` after the turn. Steps go to stderr so
    they don't tangle with streamed assistant text on stdout.
    """
    if stream:
        streamed = False
        final_answer: str | None = None
        for event in loop.run_stream(user_input):
            if event.type == "text_delta" and event.text:
                print(event.text, end="", flush=True)
                streamed = True
            elif (
                event.type == "tool_step"
                and show_steps
                and event.tool_call is not None
                and event.tool_result is not None
            ):
                _print_tool_step(
                    event.tool_call.name,
                    event.tool_call.input,
                    event.tool_result.content,
                    bool(event.tool_result.is_error),
                )
            elif event.type == "done" and event.result is not None:
                final_answer = event.result.answer
        if streamed:
            print()
            return
        print(final_answer or "(no answer)")
        return
    result = loop.run(user_input)
    if show_steps:
        _print_steps_from_result(result)
    print(result.answer or "(no answer)")


def _drive_repl_session(
    loop: AgentLoop,
    *,
    stream: bool,
    session_memory: SessionMemory,
    session_mem_path: Path,
    max_turns: int | None = None,
    show_steps: bool = False,
) -> int:
    """Drive the interactive read-input/run-turn loop on a pre-built loop.

    Pulled out of ``_run_repl`` so ``openai_cli`` can supply its own
    ``AgentLoop`` (wired to ``OpenAIProvider``) while sharing every
    slash-command, KeyboardInterrupt, EOF, auto-learn-cue, and
    session-memory-save behaviour exactly. The function returns 0 on a
    clean ``/exit`` / EOF and never raises ``KeyboardInterrupt``.

    ``max_turns`` caps the number of user turns before a clean exit (same
    path as ``/exit``). Slash commands do not count as turns. When None
    (default) the loop runs until EOF or ``/exit``.
    """
    _turn_count = 0

    def _save_session() -> None:
        try:
            session_memory.dump_json(session_mem_path)
        except OSError as err:
            print(f"(warning: could not save session memory: {err})")

    while True:
        if max_turns is not None and _turn_count >= max_turns:
            _save_session()
            return 0

        line = _read_input_line()
        if line is None:
            print()
            _save_session()
            return 0

        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("/"):
            signal = _handle_slash_command(stripped, loop)
            if signal == "exit":
                _save_session()
                return 0
            continue

        cue = detect_cue(stripped, tracer=loop._tracer)
        if cue is not None:
            print(format_hint(cue))

        try:
            _run_turn(loop, stripped, stream, show_steps=show_steps)
        except KeyboardInterrupt:
            print("\n(interrupted; transcript preserved)")
            continue

        _turn_count += 1


def _run_repl(
    *,
    workspace: Path,
    max_steps: int | None,
    max_context_tokens: int | None,
    reserved_output_tokens: int | None,
    stream: bool,
    microcompact_keep_recent: int | None = None,
    microcompact_minutes: int | None = None,
    output_headroom: int | None = None,
    compact_headroom: int | None = None,
    min_session_tokens: int | None = None,
    snip_nudge_growth_tokens: int | None = None,
    resume: str | None = None,
    shell_mode: ShellMode = ShellMode.MOCK,
    verbose: bool = False,
    aggressive_thresholds: bool = False,
    extract_memories_enabled: bool = False,
    extract_throttle_n: int = 1,
    session_memory_enabled: bool = False,
    show_steps: bool = False,
    summarizer_mode: str = "auto",
    todo_nudge_enabled: bool = True,
    todo_reminder_turns: int | None = None,
) -> int:
    """Run the interactive REPL.

    Builds one shared ``AgentLoop`` and calls it repeatedly with each user
    input. Slash commands intercept before the loop is invoked. EOF on
    stdin and ``/exit`` / ``/quit`` both terminate cleanly.

    KeyboardInterrupt during a single turn is caught and reported; the
    transcript and the loop instance are preserved so the next turn sees
    every prior user message.

    When ``resume`` is set the named session is loaded before reading user
    input. A missing or corrupted session causes ``_run_repl`` to return
    nonzero so the operator sees the failure immediately, matching the M4
    exit-gate contract.
    """
    print(_REPL_BANNER, end="")
    print(f"Workspace: {workspace}")
    if aggressive_thresholds:
        print(_format_aggressive_banner())
    print()

    # Each REPL session owns a fresh slot in the per-process loop log.
    _LAST_LOOPS.clear()
    session_mem_path = _session_memory_path(workspace)
    session_memory = SessionMemory.load_json(session_mem_path)
    tracer: Tracer = StderrTracer() if verbose else NullTracer()
    project_memory = _open_project_memory(workspace, tracer=tracer)
    loop = _build_repl_loop(
        workspace,
        max_steps=max_steps,
        max_context_tokens=max_context_tokens,
        reserved_output_tokens=reserved_output_tokens,
        microcompact_keep_recent=microcompact_keep_recent,
        microcompact_minutes=microcompact_minutes,
        output_headroom=output_headroom,
        compact_headroom=compact_headroom,
        min_session_tokens=min_session_tokens,
        snip_nudge_growth_tokens=snip_nudge_growth_tokens,
        session_memory=session_memory,
        project_memory=project_memory,
        shell_mode=shell_mode,
        tracer=tracer,
        aggressive_thresholds=aggressive_thresholds,
        extract_memories_enabled=extract_memories_enabled,
        extract_throttle_n=extract_throttle_n,
        session_memory_enabled=session_memory_enabled,
        summarizer_mode=summarizer_mode,
        todo_nudge_enabled=todo_nudge_enabled,
        todo_reminder_turns=todo_reminder_turns,
    )

    if resume is not None:
        resume_rc = _apply_resume(resume, loop)
        if resume_rc != 0:
            return resume_rc

    return _drive_repl_session(
        loop,
        stream=stream,
        session_memory=session_memory,
        session_mem_path=session_mem_path,
        show_steps=show_steps,
    )


# ---------------------------------------------------------------------------
# Argparse routing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simple-agent",
        description=(
            "simple_coding_agent: one-shot demo by default, or a multi-turn "
            "REPL with --repl. Also exposes `memory` and other subcommands."
        ),
    )
    parser.add_argument(
        "--repl",
        action="store_true",
        help="Start an interactive REPL using MockProvider.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream assistant text as it arrives (REPL mode).",
    )
    parser.add_argument(
        "--show-steps",
        action="store_true",
        help=(
            "Print each tool call and its result preview to stderr as the "
            "turn progresses (REPL mode). Pairs cleanly with --verbose."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Stream `[trace] [<channel>] k=v ...` lines to stderr for "
            "each compaction, snip, externalize, memory-select, and "
            "auto-learn cue (REPL mode)."
        ),
    )
    parser.add_argument(
        "--aggressive-thresholds",
        action="store_true",
        help=(
            "Lower every relevant context/memory threshold to demo-friendly "
            "values so compact / microcompact / snip / externalize actually "
            "fire in short REPL sessions. Explicit --max-context-tokens / "
            "--reserved-output-tokens / --max-steps still win per-field."
        ),
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Workspace path. Defaults to a fresh tempdir.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Max tool-using iterations per user turn (default: 10).",
    )
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        default=None,
        help=(
            "ContextBudget.max_tokens (default: 200_000). If "
            "--aggressive-thresholds is also set and you do not pass this "
            "flag, the preset value applies; otherwise the built-in default "
            "applies."
        ),
    )
    parser.add_argument(
        "--reserved-output-tokens",
        type=int,
        default=None,
        help=(
            "ContextBudget.reserved_output_tokens (default: 8_192). If "
            "--aggressive-thresholds is also set and you do not pass this "
            "flag, the preset value applies; otherwise the built-in default "
            "applies."
        ),
    )
    parser.add_argument(
        "--microcompact-keep-recent",
        type=int,
        default=None,
        help=(
            "MicroCompactor.keep_recent: preserve the N most recent compactable "
            "tool_results during cold-cache cleanup (default: 5). 0 clears all."
        ),
    )
    parser.add_argument(
        "--microcompact-minutes",
        type=int,
        default=None,
        metavar="N",
        help=(
            "MicroCompactor.threshold_minutes: clear compactable tool_results "
            "older than N minutes (default: 60). 0 clears on the next turn. "
            "If --aggressive-thresholds is also set and you do not pass this "
            "flag, the preset value applies; otherwise the built-in default "
            "applies."
        ),
    )
    parser.add_argument(
        "--output-headroom",
        type=int,
        default=None,
        help=(
            "ContextCompactor output headroom tokens subtracted from the "
            "context window in the auto-compact trigger (default: 12_000)."
        ),
    )
    parser.add_argument(
        "--compact-headroom",
        type=int,
        default=None,
        help=(
            "ContextCompactor compact headroom tokens subtracted from the "
            "context window in the auto-compact trigger (default: 20_000)."
        ),
    )
    parser.add_argument(
        "--min-session-tokens",
        type=int,
        default=None,
        help=(
            "ContextCompactor floor: auto-compact's formula trigger only fires "
            "once used tokens reach this minimum (default: 30_000)."
        ),
    )
    parser.add_argument(
        "--snip-nudge-growth-tokens",
        type=int,
        default=None,
        help=(
            "AgentLoop.snip_nudge_growth_tokens: arm the model-driven "
            "snip_history nudge once context grows this many tokens since the "
            "last snip (default: 10_000). Lower it (e.g. 500) WITH a roomy "
            "--max-context-tokens to exercise model snips without auto-compact "
            "preempting them. Not part of --aggressive-thresholds."
        ),
    )
    parser.add_argument(
        "--session-memory",
        action="store_true",
        default=False,
        dest="session_memory",
        help=(
            "Enable session-memory state: incremental SM fold at stop hook "
            "so compaction reuses the warm summary (O(0) provider calls). "
            "Default OFF — mirrors extract_memories_enabled opt-in pattern."
        ),
    )
    parser.add_argument(
        "--extract-memories",
        action="store_true",
        default=None,
        help=(
            "Enable automatic memory extraction after each turn. "
            "Also honoured via env SIMPLE_AGENT_EXTRACT_MEMORIES=1."
        ),
    )
    parser.add_argument(
        "--extract-throttle",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Run extraction at most once every N turns (default 1). "
            "Also honoured via env SIMPLE_AGENT_EXTRACT_THROTTLE."
        ),
    )
    parser.add_argument(
        "--resume",
        default=None,
        metavar="NAME",
        help=(
            "Resume a previously saved REPL session by name. Looks under "
            "$SIMPLE_AGENT_SESSIONS_DIR (default ~/.simple-agent/sessions/)."
        ),
    )
    parser.add_argument(
        "--shell-mode",
        choices=("mock", "allowlist"),
        default="mock",
        help=(
            "Shell tool execution mode. 'mock' (default) is safe and "
            "deterministic; 'allowlist' actually executes the 5-command "
            "allowlist (pwd, ls, cat, grep, python -m pytest)."
        ),
    )
    parser.add_argument(
        "--summarizer",
        choices=("auto", "rule", "llm"),
        default="auto",
        help=(
            "Compaction summarizer. 'auto' (default) reuses the active "
            "real provider (e.g. via openai-agent) for LLM-based "
            "summarization; falls back to RuleBasedSummarizer when only "
            "MockProvider is available (the simple-agent default). 'rule' "
            "forces RuleBasedSummarizer (no extra API call). 'llm' forces "
            "LLMSummarizer (errors at startup if no real provider is "
            "configured)."
        ),
    )
    parser.add_argument(
        "--no-todo-reminder",
        action="store_true",
        default=False,
        help="Disable the turn-based TodoWrite reminder (plan-surface M1).",
    )
    parser.add_argument(
        "--todo-reminder-turns",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Override the number of assistant turns between todo reminders "
            "(default: 10). Only applies when --no-todo-reminder is not set."
        ),
    )
    return parser


def _resolve_workspace_arg(raw: str | None) -> Path:
    if raw is None:
        # No workspace given -> fresh tempdir.
        tmp = tempfile.mkdtemp(prefix="simple-agent-repl-")
        return Path(tmp)
    workspace = Path(raw).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``simple-agent`` console script.

    Routing rules:
      * ``simple-agent memory ...``   -> ``memory_cli.main(argv_after_memory)``
      * ``simple-agent --repl ...``   -> ``_run_repl(...)``
      * ``simple-agent``              -> one-shot MockProvider demo.
    """
    args_in = list(argv) if argv is not None else sys.argv[1:]

    # Subcommand dispatch: `memory ...` runs the memory CLI without our flags.
    if args_in and args_in[0] == "memory":
        from .memory_cli import main as memory_main
        return memory_main(args_in[1:])

    parser = _build_parser()
    args = parser.parse_args(args_in)

    shell_mode = ShellMode[str(args.shell_mode).upper()]

    if args.repl or args.resume is not None:
        workspace = _resolve_workspace_arg(args.workspace)
        extract_enabled = bool(args.extract_memories) or bool(
            os.environ.get("SIMPLE_AGENT_EXTRACT_MEMORIES", "")
        )
        extract_throttle = args.extract_throttle or int(
            os.environ.get("SIMPLE_AGENT_EXTRACT_THROTTLE", "1")
        )
        return _run_repl(
            workspace=workspace,
            max_steps=args.max_steps,
            max_context_tokens=args.max_context_tokens,
            reserved_output_tokens=args.reserved_output_tokens,
            microcompact_keep_recent=args.microcompact_keep_recent,
            microcompact_minutes=args.microcompact_minutes,
            output_headroom=args.output_headroom,
            compact_headroom=args.compact_headroom,
            min_session_tokens=args.min_session_tokens,
            snip_nudge_growth_tokens=args.snip_nudge_growth_tokens,
            stream=bool(args.stream),
            resume=args.resume,
            shell_mode=shell_mode,
            verbose=bool(args.verbose),
            aggressive_thresholds=bool(args.aggressive_thresholds),
            extract_memories_enabled=extract_enabled,
            extract_throttle_n=extract_throttle,
            session_memory_enabled=bool(args.session_memory),
            show_steps=bool(args.show_steps),
            summarizer_mode=str(args.summarizer),
            todo_nudge_enabled=not bool(args.no_todo_reminder),
            todo_reminder_turns=args.todo_reminder_turns,
        )

    # One-shot demo (unchanged behavior; default shell_mode is MOCK).
    with tempfile.TemporaryDirectory(prefix="simple-agent-demo-") as tmp:
        return _run_demo(Path(tmp), shell_mode=shell_mode)


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
