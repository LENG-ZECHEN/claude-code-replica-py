"""
Tracer: per-event live trace surface for context-management mechanisms.

Source mapping:
  Tracer        <- live-trace surface complementing MetricsCollector
                   (metrics.py records post-hoc counters; the tracer emits
                   one structured line per mechanism fire so a `--verbose`
                   REPL session can show what is happening while it happens)

Two production implementations are provided:

  ``NullTracer`` is the default at every fire site -- its ``emit`` body
  is literally ``pass`` so the production code path has zero overhead and
  zero behavioral change.

  ``StderrTracer`` writes one line per emit to a given stream
  (``sys.stderr`` by default) in the locked format:

      [trace] [<channel>] key1=value1 key2=value2

  Keys are sorted alphabetically so callers can match exact strings in
  tests without worrying about kwarg insertion order. No quoting, no
  escaping; trace lines are advisory diagnostic output.

Channel names align with ``MetricsCollector`` counter names where the
two surfaces overlap. The locked channel vocabulary for this milestone
is: ``compact``, ``reactive``, ``microcompact``, ``snip``,
``externalize``, ``memory_select``, ``claude_md``, ``auto_learn``,
``budget``.

Hard invariant: fire sites MUST NOT pass raw user input or raw LLM
output text as field values. Only metadata (counts, token estimates,
entry names, scores, tool IDs) is permitted.
"""

from __future__ import annotations

import sys
from typing import Any, Protocol, TextIO, runtime_checkable


@runtime_checkable
class Tracer(Protocol):
    """Structural protocol for the per-event trace surface."""

    def emit(self, channel: str, /, **fields: Any) -> None:
        """Record one event on ``channel`` with the given metadata fields."""
        ...


class NullTracer:
    """No-op tracer used everywhere by default.

    Methods must remain trivial -- no logging, no string formatting, no
    lazy imports with side effects -- so the production code path stays
    free of behavioral change.
    """

    def emit(self, channel: str, /, **fields: Any) -> None:  # noqa: ARG002
        pass


class StderrTracer:
    """Writes one ``[trace] [<channel>] k=v ...`` line per emit to a stream."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stderr

    def emit(self, channel: str, /, **fields: Any) -> None:
        if fields:
            rendered = " ".join(
                f"{key}={fields[key]}" for key in sorted(fields)
            )
            line = f"[trace] [{channel}] {rendered}\n"
        else:
            line = f"[trace] [{channel}]\n"
        self._stream.write(line)
        # Flush so live REPL viewers see the line immediately rather than
        # only when the buffer fills. ``sys.stderr`` is line-buffered when
        # connected to a terminal but block-buffered when redirected.
        flush = getattr(self._stream, "flush", None)
        if flush is not None:
            flush()


__all__ = ["NullTracer", "StderrTracer", "Tracer"]
