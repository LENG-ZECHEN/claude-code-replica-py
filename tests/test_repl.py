"""M1-A1/A3/A4: REPL tests — written before implementation (TDD).

Covers Section 3.1 of RUNTIME_ACTIVATION_PLAN.md:
 - `--repl` flag dispatches into a REPL handler that shares one AgentLoop
   across user inputs.
 - Slash commands: `/exit` (and `/quit`), `/help`, unknown-command hint.
 - EOF on stdin, KeyboardInterrupt during a turn, empty input.
 - `--max-steps`, `--max-context-tokens`, `--reserved-output-tokens` flag
   propagation into the AgentLoop / ContextBudget.

All cases use MockProvider for determinism — no real provider, no API key,
no real shell, no real user CLAUDE.md (loader is monkeypatched).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

import simple_coding_agent.claude_md as cm
import simple_coding_agent.cli as cli_mod
from simple_coding_agent.cli import main
from simple_coding_agent.coding_tools import WorkspaceBoundaryError
from simple_coding_agent.context import ContextBudget
from simple_coding_agent.provider import MockProvider, ProviderResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_user_claude_md(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Never touch ~/.claude/CLAUDE.md during REPL tests."""
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")


def _captured_loops() -> list[Any]:
    """Snapshot of AgentLoop instances that the REPL constructed.

    The REPL records each loop it created on cli._LAST_LOOPS so tests can
    inspect token budget / max_steps without monkeypatching constructors.
    """
    return list(getattr(cli_mod, "_LAST_LOOPS", []))


def _set_stdin(
    monkeypatch: pytest.MonkeyPatch, *lines: str,
) -> None:
    """Wire stdin so REPL reads the given lines in order (then hits EOF)."""
    buffer = "\n".join(lines)
    if buffer and not buffer.endswith("\n"):
        buffer = buffer + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(buffer))


def _scripted_provider_factory(
    *responses: ProviderResponse,
) -> MockProvider:
    """Build a single MockProvider preloaded with end_turn responses."""
    script = list(responses) or [MockProvider.direct_answer("ok")]
    return MockProvider(script)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_repl_carries_transcript_across_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange: two user inputs in one REPL session.
    _set_stdin(monkeypatch, "first question", "second question", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])

    captured = capsys.readouterr()
    loops = _captured_loops()

    # Assert: same loop carries both inputs in its transcript.
    assert rc == 0, captured.out + captured.err
    assert len(loops) == 1
    transcript_msgs = loops[0]._transcript.all_messages()
    user_texts = [m.content for m in transcript_msgs if m.role.value == "user"
                  and isinstance(m.content, str)]
    assert "first question" in user_texts
    assert "second question" in user_texts


def test_repl_exit_command_returns_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0


def test_repl_quit_alias_works(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/quit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0


def test_repl_help_lists_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/help", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "/exit" in out
    assert "/help" in out
    assert "/stats" in out


def test_repl_stats_prints_metric_counters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`/stats` prints every per-mechanism counter line so the exit gate is met."""
    _set_stdin(monkeypatch, "hello there", "/stats", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "full compacts" in out
    assert "reactive compacts" in out
    assert "microcompact runs" in out
    assert "snip runs" in out
    assert "externalized bytes" in out
    assert "turns recorded:" in out


def test_repl_stats_increments_after_each_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`tokens_per_turn` accumulates inside the shared loop across REPL turns."""
    _set_stdin(monkeypatch, "alpha", "beta", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])

    captured = capsys.readouterr()
    loops = _captured_loops()

    assert rc == 0, captured.out + captured.err
    assert len(loops) == 1
    metrics = loops[0]._metrics
    assert len(metrics.tokens_per_turn) == 2


def test_repl_unknown_slash_command_prints_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_stdin(monkeypatch, "/foo", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "unknown command" in out.lower()
    assert "/help" in out


def test_repl_keyboardinterrupt_does_not_drop_transcript(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    # Arrange: turn 1 succeeds; turn 2 raises KeyboardInterrupt mid-turn;
    # turn 3 succeeds. After the interrupt the REPL must still have the
    # turn-1 user message and be able to process turn 3.
    import simple_coding_agent.loop as loop_mod

    real_run = loop_mod.AgentLoop.run
    call_count = {"n": 0}

    def _flaky_run(self: Any, user_input: str) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise KeyboardInterrupt
        return real_run(self, user_input)

    monkeypatch.setattr(loop_mod.AgentLoop, "run", _flaky_run)
    _set_stdin(
        monkeypatch,
        "first ok turn",
        "interrupted turn",
        "third ok turn",
        "/exit",
    )
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0

    loops = _captured_loops()
    msgs = loops[0]._transcript.all_messages()
    user_texts = [m.content for m in msgs if m.role.value == "user"
                  and isinstance(m.content, str)]
    # Surviving turns must still be in the transcript.
    assert "first ok turn" in user_texts
    assert "third ok turn" in user_texts


def test_repl_empty_input_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "", "   ", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = _captured_loops()
    # Empty inputs do not trigger provider calls -> transcript has zero user msgs.
    msgs = loops[0]._transcript.all_messages()
    user_strings = [m for m in msgs if m.role.value == "user"
                    and isinstance(m.content, str)]
    assert user_strings == []


def test_repl_with_max_steps_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--max-steps", "50", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = _captured_loops()
    assert loops[0]._max_steps == 50


def test_repl_passes_workspace_to_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = _captured_loops()

    read_tool = loops[0]._tool_executor._registry.get("read_file")
    with pytest.raises(WorkspaceBoundaryError):
        read_tool.fn(path="../../etc/passwd")


def test_repl_long_conversation_triggers_compact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    # Arrange: a tiny context budget forces ContextCompactor.should_compact()
    # to fire on the second turn.
    big_text = "x " * 5_000  # ~10 000 chars -> ~2500 tokens by the char/4 heuristic
    answers = [
        MockProvider.direct_answer(big_text + f" turn {n}") for n in range(20)
    ]

    def _provider_factory(_workspace: Path) -> Any:
        return MockProvider(answers)

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)

    inputs = [f"turn {n}: " + big_text for n in range(20)] + ["/exit"]
    _set_stdin(monkeypatch, *inputs)

    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "5000",
        "--reserved-output-tokens", "1000",
    ])
    assert rc == 0

    loops = _captured_loops()
    # Compaction must have run at least once during the session.
    assert loops[0]._last_summary is not None


def test_repl_compact_summary_appears_in_next_system_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    big_text = "y " * 5_000
    answers = [
        MockProvider.direct_answer(big_text + f" turn {n}") for n in range(20)
    ]
    captured_provider: dict[str, MockProvider] = {}

    def _provider_factory(_workspace: Path) -> Any:
        p = MockProvider(answers)
        captured_provider["p"] = p
        return p

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)

    inputs = [f"turn {n}: " + big_text for n in range(20)] + ["/exit"]
    _set_stdin(monkeypatch, *inputs)

    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "5000",
        "--reserved-output-tokens", "1000",
    ])
    assert rc == 0

    systems = [c.system for c in captured_provider["p"].history]
    assert any("## Conversation Summary" in s for s in systems)


def test_repl_stdin_eof_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    # No newline, no /exit -> reading hits EOF immediately.
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0


def test_repl_streams_text_when_stream_flag_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    answers = [MockProvider.direct_answer("hello-stream-token")]

    def _provider_factory(_workspace: Path) -> Any:
        return MockProvider(answers)

    monkeypatch.setattr(cli_mod, "_make_repl_provider", _provider_factory)
    _set_stdin(monkeypatch, "hi", "/exit")
    rc = main(["--repl", "--stream", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hello-stream-token" in out


def test_repl_max_context_tokens_flag_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "5000",
    ])
    assert rc == 0
    loops = _captured_loops()
    assert isinstance(loops[0]._budget, ContextBudget)
    assert loops[0]._budget.max_tokens == 5000


def test_repl_reserved_output_tokens_flag_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--max-context-tokens", "8000",
        "--reserved-output-tokens", "1234",
    ])
    assert rc == 0
    loops = _captured_loops()
    assert loops[0]._budget.reserved_output_tokens == 1234


# ---------------------------------------------------------------------------
# M1: --verbose threads StderrTracer through the loop and fire sites
# ---------------------------------------------------------------------------

def test_repl_verbose_emits_budget_trace_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One turn under ``--verbose`` produces at least one ``[trace] [budget]``."""
    _set_stdin(monkeypatch, "hello", "/exit")
    rc = main(["--repl", "--verbose", "--workspace", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[trace] [budget]" in captured.err


def test_repl_verbose_emits_memory_select_when_project_memory_has_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Saving a memory entry then sending a query emits ``memory_select``."""
    _set_stdin(
        monkeypatch,
        "/remember feedback test_entry user prefers Python tests",
        "tell me about python testing",
        "/exit",
    )
    rc = main(["--repl", "--verbose", "--workspace", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[trace] [memory_select]" in captured.err


def test_repl_default_silent_no_trace_lines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without ``--verbose``, several turns yield zero ``[trace]`` lines."""
    _set_stdin(monkeypatch, "first", "second", "third", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[trace]" not in captured.err


def test_repl_verbose_threads_tracer_into_components(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The loop built under ``--verbose`` carries a StderrTracer everywhere.

    Verifies the constructor-injection path (not just the CLI flag): the
    loop's tracer is the same StderrTracer that was threaded into the
    builder, claude_md_loader, compactor, microcompactor, snip_tool, and
    project_memory.
    """
    from simple_coding_agent.trace import NullTracer, StderrTracer

    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--verbose", "--workspace", str(tmp_path)])
    assert rc == 0
    loops = _captured_loops()
    loop = loops[0]
    assert isinstance(loop._tracer, StderrTracer)
    assert isinstance(loop._microcompactor._tracer, StderrTracer)
    assert isinstance(loop._snip_tool._tracer, StderrTracer)
    assert isinstance(loop._compactor._tracer, StderrTracer)
    assert isinstance(loop._context_builder._tracer, StderrTracer)
    assert isinstance(
        loop._context_builder._claude_md_loader._tracer, StderrTracer,
    )
    assert isinstance(loop._project_memory._tracer, StderrTracer)
    # Sanity: when --verbose is absent the default is NullTracer everywhere.
    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    assert rc == 0
    null_loop = _captured_loops()[0]
    assert isinstance(null_loop._tracer, NullTracer)
    assert isinstance(null_loop._microcompactor._tracer, NullTracer)


# ---------------------------------------------------------------------------
# M2 — --aggressive-thresholds preset
# ---------------------------------------------------------------------------

def test_aggressive_thresholds_flag_lowers_every_component_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """``--aggressive-thresholds`` wires the preset into every component."""
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--aggressive-thresholds",
        "--workspace", str(tmp_path),
    ])
    assert rc == 0
    loop = _captured_loops()[0]

    preset = cli_mod._AGGRESSIVE_THRESHOLDS
    assert loop._compactor.compact_threshold == preset["compact_threshold"]
    assert loop._compactor.keep_recent == preset["keep_recent"]
    assert loop._microcompactor._threshold_minutes == preset["microcompact_minutes"]
    assert loop._snip_tool._keep_recent == preset["snip_keep_recent"]
    store = loop._context_builder._store
    assert store._max_inline_chars == preset["max_inline_chars"]
    assert store._total_budget_chars == preset["total_budget_chars"]


def test_aggressive_thresholds_banner_prints_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Banner appears once on stdout (not stderr) when preset is active."""
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--aggressive-thresholds",
        "--workspace", str(tmp_path),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "[aggressive-thresholds]" in captured.out
    # Banner content is derived from the preset dict; assert specific tokens
    # so a future preset typo cannot pass silently.
    assert "compact=0.2" in captured.out
    assert "snip_keep=1" in captured.out
    # The banner is NOT a [trace] line and must not pollute stderr.
    assert "[aggressive-thresholds]" not in captured.err


def test_aggressive_thresholds_omitted_keeps_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default REPL invocation does NOT emit the banner or apply the preset."""
    _set_stdin(monkeypatch, "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "[aggressive-thresholds]" not in captured.out
    loop = _captured_loops()[0]
    # Defaults: ContextCompactor.compact_threshold=0.8, SnipTool keep_recent=3.
    assert loop._compactor.compact_threshold == 0.8
    assert loop._snip_tool._keep_recent == 3
    assert loop._microcompactor._threshold_minutes == 60


def test_aggressive_thresholds_explicit_context_flag_overrides_preset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Explicit ``--max-context-tokens`` wins per-field; other preset values apply."""
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--aggressive-thresholds",
        "--max-context-tokens", "16000",
        "--workspace", str(tmp_path),
    ])
    assert rc == 0
    loop = _captured_loops()[0]
    # Per-field precedence: explicit flag beats preset's 4_000 value.
    assert loop._context_builder._budget.max_tokens == 16000
    # Unspecified fields still take the aggressive value.
    assert loop._snip_tool._keep_recent == 1
    assert loop._microcompactor._threshold_minutes == 1


# ---------------------------------------------------------------------------
# M2 — full 8-field aggressive-thresholds precedence matrix + bug fix
# ---------------------------------------------------------------------------
# Each _AGGRESSIVE_THRESHOLDS key maps to the component attribute that
# actually takes effect once a loop is built — so a test can read the
# *effective* value rather than trusting that the preset was wired.
_FIELD_ACCESSORS = {
    "compact_threshold": lambda loop: loop._compactor.compact_threshold,
    "keep_recent": lambda loop: loop._compactor.keep_recent,
    "microcompact_minutes": lambda loop: loop._microcompactor._threshold_minutes,
    "max_inline_chars": lambda loop: loop._context_builder._store._max_inline_chars,
    "total_budget_chars": lambda loop: loop._context_builder._store._total_budget_chars,
    "snip_keep_recent": lambda loop: loop._snip_tool._keep_recent,
    "context_tokens": lambda loop: loop._budget.max_tokens,
    "reserved_output_tokens": lambda loop: loop._budget.reserved_output_tokens,
}

# State (i) expectation: the built-in default that applies when neither a
# CLI flag nor --aggressive-thresholds is given. For the two flag-backed
# fields this is the cli module's named default constant; for the others
# it is the owning component's own default.
_FIELD_DEFAULTS = {
    "compact_threshold": 0.8,
    "keep_recent": 10,
    "microcompact_minutes": 60,
    "max_inline_chars": 50_000,
    "total_budget_chars": 200_000,
    "snip_keep_recent": 3,
    "context_tokens": cli_mod._DEFAULT_CONTEXT_TOKENS,
    "reserved_output_tokens": cli_mod._DEFAULT_RESERVED_OUTPUT_TOKENS,
}

# Only these two fields are backed by an explicit CLI flag, so only they
# get state (iii). The value names the _build_repl_loop keyword to set.
_FIELD_CLI_FLAG = {
    "context_tokens": "max_context_tokens",
    "reserved_output_tokens": "reserved_output_tokens",
}
# Explicit values chosen distinct from both default and preset so a wrong
# branch cannot coincidentally pass.
_FIELD_EXPLICIT = {"context_tokens": 16_000, "reserved_output_tokens": 999}


def _precedence_matrix_cases() -> list[Any]:
    cases: list[Any] = []
    for field in _FIELD_DEFAULTS:
        cases.append(
            pytest.param(
                field, "default", None, _FIELD_DEFAULTS[field],
                id=f"{field}-default",
            )
        )
        cases.append(
            pytest.param(
                field, "preset", None, cli_mod._AGGRESSIVE_THRESHOLDS[field],
                id=f"{field}-preset",
            )
        )
        if field in _FIELD_CLI_FLAG:
            cases.append(
                pytest.param(
                    field, "explicit", _FIELD_EXPLICIT[field],
                    _FIELD_EXPLICIT[field], id=f"{field}-explicit",
                )
            )
    return cases


@pytest.mark.parametrize(
    "field,state,explicit,expected", _precedence_matrix_cases(),
)
def test_aggressive_thresholds_precedence_matrix(
    field: str,
    state: str,
    explicit: int | None,
    expected: float,
    tmp_path: Path,
) -> None:
    """Every _AGGRESSIVE_THRESHOLDS field resolves to the right effective value.

    Three states per the M2 exit gate:
      (i)   default     — no flag, no preset            -> built-in default
      (ii)  preset      — --aggressive-thresholds only  -> preset value
      (iii) explicit    — explicit flag + preset        -> the explicit value

    State (ii) for ``context_tokens`` / ``reserved_output_tokens`` is the
    regression guard for the M2 bug: those two were always shadowed by the
    argparse defaults, so the preset never took effect.
    """
    kwargs: dict[str, Any] = {"aggressive_thresholds": state != "default"}
    if state == "explicit":
        kwargs[_FIELD_CLI_FLAG[field]] = explicit
    loop = cli_mod._build_repl_loop(tmp_path, **kwargs)
    assert _FIELD_ACCESSORS[field](loop) == expected


# ---------------------------------------------------------------------------
# M1 (ctx-pdf): the four PDF-threshold flags propagate through
# _resolve_threshold into the compactor / microcompactor.
# ---------------------------------------------------------------------------

def test_pdf_threshold_flags_default_when_omitted(tmp_path: Path) -> None:
    """Omitting the flags applies the built-in PDF defaults."""
    loop = cli_mod._build_repl_loop(tmp_path)
    assert loop._microcompactor._keep_recent == 5
    assert loop._compactor.output_headroom == 12_000
    assert loop._compactor.compact_headroom == 20_000
    assert loop._compactor.min_session_tokens == 30_000


def test_pdf_threshold_flags_explicit_values_propagate(tmp_path: Path) -> None:
    """Explicit flag values reach the components (explicit > default)."""
    loop = cli_mod._build_repl_loop(
        tmp_path,
        microcompact_keep_recent=2,
        output_headroom=1_000,
        compact_headroom=3_000,
        min_session_tokens=7_000,
    )
    assert loop._microcompactor._keep_recent == 2
    assert loop._compactor.output_headroom == 1_000
    assert loop._compactor.compact_headroom == 3_000
    assert loop._compactor.min_session_tokens == 7_000


def test_pdf_threshold_flags_parsed_by_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """End-to-end: the flags are accepted by argparse and wired into the loop."""
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--microcompact-keep-recent", "1",
        "--output-headroom", "500",
        "--compact-headroom", "1500",
        "--min-session-tokens", "9000",
    ])
    assert rc == 0
    loop = _captured_loops()[0]
    assert loop._microcompactor._keep_recent == 1
    assert loop._compactor.output_headroom == 500
    assert loop._compactor.compact_headroom == 1_500
    assert loop._compactor.min_session_tokens == 9_000


# ---------------------------------------------------------------------------
# ctx-pdf follow-up: --snip-nudge-growth-tokens (drives the model-snip nudge).
# preset_key=None (the --max-steps pattern): explicit flag or default only,
# NOT lowered by --aggressive-thresholds.
# ---------------------------------------------------------------------------

def test_snip_nudge_growth_tokens_defaults_when_omitted(tmp_path: Path) -> None:
    loop = cli_mod._build_repl_loop(tmp_path)
    assert loop._snip_nudge_growth_tokens == cli_mod._DEFAULT_SNIP_NUDGE_GROWTH_TOKENS


def test_snip_nudge_growth_tokens_explicit_value_propagates(tmp_path: Path) -> None:
    loop = cli_mod._build_repl_loop(tmp_path, snip_nudge_growth_tokens=500)
    assert loop._snip_nudge_growth_tokens == 500


def test_snip_nudge_growth_tokens_not_lowered_by_aggressive(tmp_path: Path) -> None:
    # The nudge has no _AGGRESSIVE_THRESHOLDS entry (snip is the lighter
    # alternative to a full compact, which aggressive mode fires constantly),
    # so the aggressive preset must NOT change it.
    loop = cli_mod._build_repl_loop(tmp_path, aggressive_thresholds=True)
    assert loop._snip_nudge_growth_tokens == cli_mod._DEFAULT_SNIP_NUDGE_GROWTH_TOKENS


# ---------------------------------------------------------------------------
# ctx-demo review-fix: _build_repl_loop must wire the SAME ToolResultStore into
# both ContextBuilder and AgentLoop. It previously reached only the builder, so
# AgentLoop._tool_result_store stayed None and MetricsCollector.externalized_bytes
# was stuck at 0 for every REPL session (/stats under-reported externalization).
# ---------------------------------------------------------------------------

def test_build_repl_loop_wires_tool_result_store_into_agent_loop(tmp_path: Path) -> None:
    """The loop and its context builder share one store, so /stats sees real bytes."""
    loop = cli_mod._build_repl_loop(tmp_path, aggressive_thresholds=True)
    assert loop._tool_result_store is not None
    assert loop._tool_result_store is loop._context_builder._store
    # refreshing now propagates real externalized bytes into the metrics counter
    loop._tool_result_store.process_result("regress-call", "Z" * 80_000)
    loop._refresh_externalized_bytes()
    assert loop._metrics.externalized_bytes > 0


def test_snip_nudge_growth_tokens_parsed_by_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _set_stdin(monkeypatch, "/exit")
    rc = main([
        "--repl",
        "--workspace", str(tmp_path),
        "--snip-nudge-growth-tokens", "500",
    ])
    assert rc == 0
    loop = _captured_loops()[0]
    assert loop._snip_nudge_growth_tokens == 500


# ---------------------------------------------------------------------------
# --show-steps wiring (regression: was silently dropped in REPL paths)
# ---------------------------------------------------------------------------

def _show_steps_provider_factory(_workspace: Path) -> MockProvider:
    """Two-response script: first turn calls list_files, second ends the turn."""
    return MockProvider([
        MockProvider.tool_call("list_files", {"path": "."}),
        MockProvider.direct_answer("listed the workspace"),
    ])


def test_repl_show_steps_renders_tool_calls_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_mod, "_make_repl_provider", _show_steps_provider_factory)
    _set_stdin(monkeypatch, "list please", "/exit")
    rc = main(["--repl", "--show-steps", "--workspace", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Tool: list_files" in captured.err
    # Tool may succeed (Result:) or fail (ERROR:) under the MockProvider test
    # registry — either marker proves the tool_step rendering pipeline fires.
    assert ("Result:" in captured.err) or ("ERROR:" in captured.err)
    assert "listed the workspace" in captured.out


def test_repl_without_show_steps_omits_tool_call_lines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_mod, "_make_repl_provider", _show_steps_provider_factory)
    _set_stdin(monkeypatch, "list please", "/exit")
    rc = main(["--repl", "--workspace", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Tool: list_files" not in captured.err
    assert "listed the workspace" in captured.out


def test_repl_show_steps_stream_mode_renders_tool_step_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_mod, "_make_repl_provider", _show_steps_provider_factory)
    _set_stdin(monkeypatch, "list please", "/exit")
    rc = main(["--repl", "--stream", "--show-steps", "--workspace", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Tool: list_files" in captured.err
    assert "listed the workspace" in captured.out


