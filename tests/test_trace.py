"""M1/V1: Tracer protocol — written before implementation (TDD).

Covers `src/simple_coding_agent/trace.py` plus the secret-leak invariant
that fire sites in the loop must never emit raw user input or LLM output.

All tests are deterministic and require no network or API key.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from simple_coding_agent.cli import main as cli_main
from simple_coding_agent.trace import NullTracer, StderrTracer, Tracer

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
