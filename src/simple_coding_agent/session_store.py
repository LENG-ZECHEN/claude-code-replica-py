"""M4-D2: cross-process REPL session persistence.

The REPL ``/save <name>`` and ``/load <name>`` slash commands plus the
top-level ``simple-agent --resume <name>`` flag share this module. Files
land under ``~/.simple-agent/sessions/<name>.json`` by default;
``SIMPLE_AGENT_SESSIONS_DIR`` overrides the directory for tests and
self-contained runs.

The on-disk format wraps a ``Transcript.to_jsonable()`` payload alongside
the most recent ``CompactSummary`` so a resumed loop re-injects the same
``## Conversation Summary`` text into the next system prompt — the
mechanism the M4 exit gate exercises end-to-end.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .models import CompactSummary
from .transcript import Transcript, _atomic_write_json

_SESSION_VERSION = 1
_SESSIONS_DIR_ENV = "SIMPLE_AGENT_SESSIONS_DIR"
_DEFAULT_SESSIONS_DIR = "~/.simple-agent/sessions"
_SAFE_SESSION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class InvalidSessionNameError(ValueError):
    """Raised when a user-supplied session name fails validation."""


class SessionNotFoundError(FileNotFoundError):
    """Raised when ``load_session`` cannot find the named file."""


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def resolve_sessions_dir() -> Path:
    """Return the directory that holds named-session JSON files."""
    raw = os.environ.get(_SESSIONS_DIR_ENV) or _DEFAULT_SESSIONS_DIR
    return Path(raw).expanduser()


def is_valid_session_name(name: str) -> bool:
    """True iff ``name`` is safe to use as a filesystem-bound session id.

    Rejects path separators, leading dots, and anything outside the
    ``[A-Za-z0-9][A-Za-z0-9_-]{0,127}`` alphabet — mirroring the
    ``_SAFE_ENTRY_ID_PATTERN`` already used by ``ProjectMemory``.
    """
    return bool(_SAFE_SESSION_NAME_PATTERN.fullmatch(name))


def session_path_for(name: str) -> Path:
    """Resolve ``<sessions_dir>/<name>.json`` for ``name``."""
    if not is_valid_session_name(name):
        raise InvalidSessionNameError(f"invalid session name: {name!r}")
    return resolve_sessions_dir() / f"{name}.json"


# ---------------------------------------------------------------------------
# CompactSummary <-> dict
# ---------------------------------------------------------------------------


def _summary_to_dict(summary: CompactSummary | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "boundary_uuid": summary.boundary_uuid,
        "summary_text": summary.summary_text,
        "messages_summarized": summary.messages_summarized,
        "pre_token_count": summary.pre_token_count,
        "post_token_count": summary.post_token_count,
        "restored_files": list(summary.restored_files),
        "timestamp": summary.timestamp,
    }


def _summary_from_dict(raw: Any) -> CompactSummary | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("session file 'last_summary' must be a JSON object or null")
    required = (
        "boundary_uuid",
        "summary_text",
        "messages_summarized",
        "pre_token_count",
        "post_token_count",
    )
    for field_name in required:
        if field_name not in raw:
            raise ValueError(
                f"session file 'last_summary' missing required field {field_name!r}",
            )
    restored_files_raw = raw.get("restored_files", [])
    if not isinstance(restored_files_raw, list):
        raise ValueError("session file 'last_summary.restored_files' must be a list")
    kwargs: dict[str, Any] = {
        "boundary_uuid": str(raw["boundary_uuid"]),
        "summary_text": str(raw["summary_text"]),
        "messages_summarized": int(raw["messages_summarized"]),
        "pre_token_count": int(raw["pre_token_count"]),
        "post_token_count": int(raw["post_token_count"]),
        "restored_files": [str(p) for p in restored_files_raw],
    }
    timestamp = raw.get("timestamp")
    if timestamp is not None:
        kwargs["timestamp"] = str(timestamp)
    return CompactSummary(**kwargs)


# ---------------------------------------------------------------------------
# save / load
# ---------------------------------------------------------------------------


def save_session(
    path: str | Path,
    *,
    transcript: Transcript,
    last_summary: CompactSummary | None,
) -> None:
    """Atomically persist a transcript + last summary to ``path``."""
    target = Path(path)
    payload = {
        "version": _SESSION_VERSION,
        "transcript": transcript.to_jsonable(),
        "last_summary": _summary_to_dict(last_summary),
    }
    _atomic_write_json(target, payload)


def load_session(
    path: str | Path,
) -> tuple[Transcript, CompactSummary | None]:
    """Inverse of ``save_session``.

    Raises ``SessionNotFoundError`` when ``path`` is missing so REPL
    callers can render ``no such session`` without a try/except over
    ``FileNotFoundError`` from the JSON layer. Schema violations raise
    ``ValueError`` (consistent with ``Transcript.load_json``).
    """
    target = Path(path)
    if not target.exists():
        raise SessionNotFoundError(f"no such session file: {target}")
    with open(target, encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"session file at {target} must contain a JSON object")
    transcript_payload = payload.get("transcript")
    if not isinstance(transcript_payload, dict):
        raise ValueError(f"session file at {target} has no 'transcript' object")
    transcript = Transcript.from_jsonable(transcript_payload)
    last_summary = _summary_from_dict(payload.get("last_summary"))
    return transcript, last_summary


__all__ = [
    "InvalidSessionNameError",
    "SessionNotFoundError",
    "is_valid_session_name",
    "load_session",
    "resolve_sessions_dir",
    "save_session",
    "session_path_for",
]
