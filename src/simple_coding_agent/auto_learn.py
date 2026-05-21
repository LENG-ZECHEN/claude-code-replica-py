"""
P9-M5 / B4: Detect cues in user input that suggest saving as memory.

Pattern detection only -- no side effects, no I/O, no provider call. The
REPL consumes this signal to print a one-line hint to the user (e.g.
"detected '记住' cue -- use /remember <type> <id> <body> to persist"),
matching Claude Code's headline auto-learn behaviour but stopping short
of actually writing without explicit user action.

Cues:
  - ``记住`` / ``以后``  : Chinese imperative learning markers
  - ``don't``           : negative preference (apostrophe variants)
  - ``prefer``          : positive preference (and morphological siblings)

Detection is greedy on the FIRST matching cue, returning the canonical
label so callers can render a stable hint regardless of surface form.
"""

from __future__ import annotations

import re

# (label, compiled pattern). Order matters: CJK markers checked first
# because they are unambiguous; English cues use word boundaries so they
# do not match inside unrelated tokens (e.g. ``preference`` matches,
# ``prefers`` matches, ``preferential`` does not without explicit anchor).
_CUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("记住", re.compile(r"记住")),
    ("以后", re.compile(r"以后")),
    # ``don't`` / ``dont`` / ``don’t`` (curly apostrophe). The
    # closing-quote variants are common from mobile keyboards.
    ("don't", re.compile(r"(?i)\bdon[’']?t\b")),
    ("prefer", re.compile(r"(?i)\bprefer(?:s|red|ence|ences)?\b")),
)


def detect_cue(text: str) -> str | None:
    """Return the canonical cue label found in ``text``, or ``None``.

    The function never raises and never mutates ``text``. An empty string
    yields ``None``.
    """
    if not text:
        return None
    for label, pattern in _CUE_PATTERNS:
        if pattern.search(text):
            return label
    return None


def format_hint(cue: str) -> str:
    """Render the one-line hint shown to the user when a cue is detected."""
    return (
        f"(cue detected: {cue!r} -- type "
        f"/remember <type> <id> <body> to persist to project memory)"
    )


__all__ = ["detect_cue", "format_hint"]
