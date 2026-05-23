"""M1/V1: Tracer protocol — written before implementation (TDD).

Covers `src/simple_coding_agent/trace.py` plus the secret-leak invariant
that fire sites in the loop must never emit raw user input or LLM output.

All tests are deterministic and require no network or API key.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from simple_coding_agent.cli import main as cli_main
from simple_coding_agent.provider import MockProvider, PromptTooLongError
from simple_coding_agent.trace import (
    NullTracer,
    StderrTracer,
    Tracer,
    _render_value,
)

# ---------------------------------------------------------------------------
# NullTracer
# ---------------------------------------------------------------------------

def test_null_tracer_emit_is_noop() -> None:
    """NullTracer.emit must accept arbitrary kwargs and return None silently."""
    tracer = NullTracer()
    # No exception, no return value.
    assert tracer.emit("compact", count=1, tokens=42) is None
    assert tracer.emit("anything", a="b") is None
    assert tracer.emit("empty") is None


def test_null_tracer_satisfies_protocol() -> None:
    """NullTracer is a structural Tracer."""
    tracer: Tracer = NullTracer()
    tracer.emit("snip", n=2)


# ---------------------------------------------------------------------------
# StderrTracer
# ---------------------------------------------------------------------------

def test_stderr_tracer_writes_one_line_per_emit() -> None:
    """One emit -> one line on the configured stream."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    tracer.emit("budget", tokens=100, dropped=0)
    lines = buf.getvalue().splitlines()
    assert len(lines) == 1


def test_stderr_tracer_line_format_locked() -> None:
    """Exact format: ``[trace] [<channel>] k1=v1 k2=v2`` with sorted keys."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    tracer.emit("compact", messages=4, tokens=2048)
    line = buf.getvalue().rstrip("\n")
    # Keys must be sorted alphabetically: messages before tokens.
    assert line == "[trace] [compact] messages=4 tokens=2048"


def test_stderr_tracer_zero_fields() -> None:
    """A bare emit produces the channel line without trailing space."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    tracer.emit("microcompact")
    line = buf.getvalue().rstrip("\n")
    assert line == "[trace] [microcompact]"


def test_stderr_tracer_multiple_emits_append() -> None:
    """Successive emits append lines; earlier lines stay intact."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    tracer.emit("snip", count=1)
    tracer.emit("budget", tokens=99)
    lines = buf.getvalue().splitlines()
    assert lines == [
        "[trace] [snip] count=1",
        "[trace] [budget] tokens=99",
    ]


def test_stderr_tracer_keys_sorted_deterministic() -> None:
    """Field ordering is deterministic regardless of kwarg insertion order."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    tracer.emit("memory_select", zebra=1, alpha=2, mu=3)
    line = buf.getvalue().rstrip("\n")
    assert line == "[trace] [memory_select] alpha=2 mu=3 zebra=1"


def test_stderr_tracer_default_stream_is_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Omitting `stream=` writes to sys.stderr."""
    tracer = StderrTracer()
    tracer.emit("auto_learn", cue_label="prefer")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[trace] [auto_learn] cue_label=prefer" in captured.err


# ---------------------------------------------------------------------------
# Channel-name coverage (channels must align with MetricsCollector)
# ---------------------------------------------------------------------------

def test_stderr_tracer_accepts_locked_channels() -> None:
    """All 9 documented channels round-trip through emit without error."""
    channels = (
        "compact", "reactive", "microcompact", "snip",
        "externalize", "memory_select", "claude_md",
        "auto_learn", "budget",
    )
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    for ch in channels:
        tracer.emit(ch, n=1)
    lines = buf.getvalue().splitlines()
    assert len(lines) == len(channels)
    for ch, line in zip(channels, lines, strict=True):
        assert line.startswith(f"[trace] [{ch}]")


# ---------------------------------------------------------------------------
# Secret-leak invariant
# ---------------------------------------------------------------------------

def test_stderr_tracer_line_ends_with_newline() -> None:
    """Each emitted line is terminated with a single ``\\n``."""
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    tracer.emit("compact", n=1)
    text = buf.getvalue()
    assert text.endswith("\n")
    assert text.count("\n") == 1


def test_null_tracer_runtime_isinstance_check() -> None:
    """``isinstance(..., Tracer)`` works at runtime for both impls."""
    assert isinstance(NullTracer(), Tracer)
    assert isinstance(StderrTracer(stream=io.StringIO()), Tracer)


def test_stderr_tracer_flushes_after_each_emit() -> None:
    """Each emit calls ``flush()`` so live viewers see the line immediately."""

    class _RecordingStream:
        def __init__(self) -> None:
            self.buf: list[str] = []
            self.flush_calls = 0

        def write(self, text: str) -> int:
            self.buf.append(text)
            return len(text)

        def flush(self) -> None:
            self.flush_calls += 1

    stream = _RecordingStream()
    tracer = StderrTracer(stream=stream)  # type: ignore[arg-type]
    tracer.emit("budget", tokens=1)
    tracer.emit("snip", count=2)
    assert stream.flush_calls == 2
    assert "[trace] [budget] tokens=1\n" in stream.buf
    assert "[trace] [snip] count=2\n" in stream.buf


def test_stderr_tracer_no_raw_user_input_through_repl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sensitive substrings in user input must never appear on stderr.

    Drives ``simple-agent --repl --verbose`` end-to-end. The hard rule is
    that trace lines emit only metadata (counts, IDs, scores). If any
    fire-site ever stringified user content into a trace field, that
    secret would appear in captured stderr.
    """
    secret = "sk-AAAA1234SECRET"
    user_line = f"please remember my key is {secret} and prefer Python"

    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(user_line + "\n/exit\n"),
    )

    rc = cli_main([
        "--repl", "--verbose", "--workspace", str(tmp_path),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert secret not in captured.err
    assert secret not in captured.out
    # Sanity: --verbose must have produced *some* stderr trace lines.
    assert "[trace]" in captured.err


# ---------------------------------------------------------------------------
# _render_value helper (M1 Change 2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(42, "42", id="int"),
        pytest.param(0, "0", id="int-zero"),
        pytest.param(-7, "-7", id="int-negative"),
        pytest.param(3.5, "3.5", id="float"),
        pytest.param(True, "True", id="bool-true"),
        pytest.param(False, "False", id="bool-false"),
        pytest.param(None, "None", id="none"),
        pytest.param("plain", "plain", id="str-no-whitespace"),
        pytest.param("", "", id="str-empty"),
        pytest.param("has space", "'has space'", id="str-with-space"),
        pytest.param("tab\there", "'tab\\there'", id="str-with-tab"),
        pytest.param({"a": 1, "b": 2}, "{'a': 1, 'b': 2}", id="dict"),
        pytest.param([1, 2, 3], "[1, 2, 3]", id="list"),
    ],
)
def test_render_value(value: Any, expected: str) -> None:
    """_render_value: scalars via str, whitespace-strings/other types via repr."""
    assert _render_value(value) == expected


def test_render_value_whitespace_string_is_quoted() -> None:
    """A whitespace-containing string must come back repr-quoted, not raw."""
    rendered = _render_value("prefer Python 3")
    assert rendered == "'prefer Python 3'"
    assert rendered.startswith("'") and rendered.endswith("'")


def test_render_value_bool_is_not_rendered_as_int() -> None:
    """bool is an int subclass; it must render as ``True``/``False`` via str."""
    assert _render_value(True) == "True"
    assert _render_value(False) == "False"


# ---------------------------------------------------------------------------
# (a) Secret-leak negative test across realistic secret shapes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "secret",
    [
        pytest.param("Bearer eyJhbGciOiJIUzI1Ni004FAKE", id="bearer-token"),
        pytest.param("AKIAIOSFODNN7EXAMPLE", id="aws-key"),
        pytest.param(
            "sk-proj-" + "A1b2C3d4E5" * 6,
            id="openai-key",
        ),
        pytest.param("用户密钥 张伟SECRET密码", id="unicode-secret"),
    ],
)
def test_secret_leak_negative(
    secret: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No secret shape may leak onto stderr after passing through the REPL.

    Fire sites emit only metadata; if any ever stringified user content
    into a trace field, the secret would surface in captured stderr.
    """
    user_line = f"please remember my key is {secret} and prefer Python"

    import simple_coding_agent.claude_md as cm
    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr("sys.stdin", io.StringIO(user_line + "\n/exit\n"))

    rc = cli_main(["--repl", "--verbose", "--workspace", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert secret not in captured.err
    assert secret not in captured.out
    # --verbose must still have produced trace output (proves the path ran).
    assert "[trace]" in captured.err


# ---------------------------------------------------------------------------
# (b) Closed-stream guard: a dead writer must not crash the agent
# ---------------------------------------------------------------------------

def test_stream_closed_does_not_propagate() -> None:
    """Emitting to an already-closed stream must swallow OSError/ValueError."""
    closed = io.StringIO()
    closed.close()
    tracer = StderrTracer(stream=closed)
    # Must not raise: a closed StringIO raises ValueError on write/flush.
    tracer.emit("budget", tokens=100, dropped=0)
    tracer.emit("reactive")  # zero-field path must also be safe


def test_stream_closed_only_swallows_io_errors() -> None:
    """The guard catches (OSError, ValueError) only — not arbitrary errors."""

    class _AngryStream:
        def write(self, text: str) -> int:
            raise RuntimeError("not an I/O error")

        def flush(self) -> None:  # pragma: no cover - never reached
            pass

    tracer = StderrTracer(stream=_AngryStream())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        tracer.emit("budget", tokens=1)


# ---------------------------------------------------------------------------
# (c) Reactive channel end-to-end through a one-turn REPL
# ---------------------------------------------------------------------------

class _ReactiveProvider:
    """First call raises PromptTooLongError; subsequent calls succeed.

    Mirrors ``tests/test_stress_full_compact._PromptTooLongScriptedProvider``
    but local to this module to avoid cross-test coupling.
    """

    def __init__(self) -> None:
        self._calls = 0

    def call(self, system: str, messages: list[Any], tools: list[Any]) -> Any:
        self._calls += 1
        if self._calls == 1:
            raise PromptTooLongError("prompt too long")
        return MockProvider.direct_answer("recovered after reactive compact")

    def stream_call(
        self, system: str, messages: list[Any], tools: list[Any]
    ) -> Iterator[Any]:  # pragma: no cover - REPL default path is non-stream
        from simple_coding_agent.provider import ProviderStreamEvent

        response = self.call(system, messages, tools)
        if response.text:
            yield ProviderStreamEvent.text_delta(response.text)
        yield ProviderStreamEvent.done(response)


def test_reactive_channel_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A reactive-compact retry must surface a ``[trace] [reactive]`` line."""
    import simple_coding_agent.claude_md as cm
    import simple_coding_agent.cli as cli_mod

    monkeypatch.setattr(cm, "_DEFAULT_USER_CLAUDE_MD", tmp_path / "no_claude.md")
    monkeypatch.setattr(
        cli_mod, "_make_repl_provider", lambda _ws: _ReactiveProvider()
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("very large request\n/exit\n"))

    rc = cli_main(["--repl", "--verbose", "--workspace", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[trace] [reactive]" in captured.err


# ---------------------------------------------------------------------------
# (d) Whitespace / non-string values round-trip through the demo parser
# ---------------------------------------------------------------------------

def _load_parse_trace_events() -> Any:
    """Load ``examples/visibility_full_demo._parse_trace_events`` by path."""
    demo_path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "visibility_full_demo.py"
    )
    spec = importlib.util.spec_from_file_location("visibility_full_demo", demo_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["visibility_full_demo"] = module
    try:
        spec.loader.exec_module(module)
        return module._parse_trace_events
    finally:
        sys.modules.pop("visibility_full_demo", None)


def test_whitespace_value_roundtrip_through_demo_parser(tmp_path: Path) -> None:
    """A whitespace value must not corrupt the adjacent field when parsed."""
    parse_trace_events = _load_parse_trace_events()
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    # 'payload' is whitespace-containing (repr-quoted); 'z' is the adjacent
    # field that must survive intact.
    tracer.emit("budget", payload={"a": 1, "b": 2}, z=99)

    stderr_path = tmp_path / "trace.stderr"
    stderr_path.write_text(buf.getvalue(), encoding="utf-8")
    events = parse_trace_events(stderr_path)

    assert "budget" in events
    assert events["budget"][0]["z"] == "99"


@pytest.mark.parametrize(
    ("payload", "adjacent"),
    [
        pytest.param({"a": 1, "b": 2}, 7, id="dict"),
        pytest.param([1, 2, 3], 8, id="list"),
        pytest.param(None, 9, id="none"),
    ],
)
def test_nonstring_value_roundtrip_through_demo_parser(
    payload: Any, adjacent: int, tmp_path: Path
) -> None:
    """dict / list / None values must not break the trailing field."""
    parse_trace_events = _load_parse_trace_events()
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    tracer.emit("budget", payload=payload, z=adjacent)

    stderr_path = tmp_path / "trace.stderr"
    stderr_path.write_text(buf.getvalue(), encoding="utf-8")
    events = parse_trace_events(stderr_path)

    assert events["budget"][0]["z"] == str(adjacent)


# ---------------------------------------------------------------------------
# 9-channel format regression with the new value rendering
# ---------------------------------------------------------------------------

def test_nine_channel_format_unchanged_for_scalar_values() -> None:
    """_render_value must leave the locked scalar format byte-identical."""
    channels = (
        "compact", "reactive", "microcompact", "snip",
        "externalize", "memory_select", "claude_md",
        "auto_learn", "budget",
    )
    buf = io.StringIO()
    tracer = StderrTracer(stream=buf)
    for ch in channels:
        tracer.emit(ch, count=2, tokens=42)
    lines = buf.getvalue().splitlines()
    assert len(lines) == len(channels)
    for ch, line in zip(channels, lines, strict=True):
        assert line == f"[trace] [{ch}] count=2 tokens=42"
