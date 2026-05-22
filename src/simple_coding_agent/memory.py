"""
MemoryStore: session-scoped and project-scoped memory with file-backed persistence.

Source mapping:
  MemoryEntry    <- memory file format in ~/.claude/projects/<slug>/memory/
  MemoryType     <- user/feedback/project/reference types from CLAUDE.md memory system
  SessionMemory  <- in-process ephemeral memory (lost when process exits)
  ProjectMemory  <- file-backed persistent memory (~/.claude/projects/<slug>/memory/)
  MEMORY.md      <- manifest index (<=200 lines per source constraint)
  to_snippets()  <- memory injection format consumed by ContextBuilder.memory_snippets

Security: save() rejects body text that looks like a secret assignment
(e.g. API_KEY=..., TOKEN=...) to prevent accidental secret persistence.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

_MANIFEST_FILENAME = "MEMORY.md"
_MAX_MANIFEST_BODY_PREVIEW = 80
_SAFE_ENTRY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Original key=value style.
    re.compile(
        r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key)\s*[=:]\s*\S+",
    ),
    # Bearer tokens, e.g. "Authorization: Bearer abc.def_123".
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=/+]{8,}"),
    # AWS access key IDs.
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # PEM block headers (matches both BEGIN and headers for any
    # PRIVATE KEY family: RSA, EC, OPENSSH, PGP, etc.).
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----"),
)
_MEMORY_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


def _check_body_for_secrets(body: str) -> None:
    """Raise ValueError if body matches any known secret pattern."""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(body):
            raise ValueError(
                "Memory body appears to contain a secret "
                "(matched a known secret pattern). "
                "Do not store secrets in memory."
            )


def _escape_markdown_link_text(text: str) -> str:
    """Escape characters in markdown link text.

    User-controlled entry names must not be able to break the
    ``[link text](url)`` form in the ``MEMORY.md`` manifest or inject
    newlines that would split the one-line-per-entry layout.
    """
    return (
        text.replace("\\", "\\\\")
            .replace("]", "\\]")
            .replace("[", "\\[")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\n", " ")
            .replace("\r", " ")
    )


class MemoryType(StrEnum):
    """Four memory categories mirroring the CLAUDE.md memory system."""
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


@dataclass
class MemoryEntry:
    """A single memory record.

    Source: memory file frontmatter in ~/.claude/projects/<slug>/memory/*.md.
    Stored as JSON here for simplicity.
    """
    name: str
    body: str
    type: MemoryType
    id: str = field(default_factory=lambda: str(_uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "body": self.body,
            "type": self.type.value,
            "tags": self.tags,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MemoryEntry:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            body=str(data["body"]),
            type=MemoryType(str(data["type"])),
            tags=[str(t) for t in v] if isinstance(v := data.get("tags", []), list) else [],
            created_at=str(data["created_at"]),
        )

    def to_snippet(self) -> str:
        """One-line format consumed by ContextBuilder.memory_snippets."""
        return f"[{self.type}] {self.name}: {self.body}"


class MemorySelector:
    """Selects memory entries relevant to the current user request."""

    def score(self, query: str, entry_text: str) -> float:
        """Jaccard similarity over lowercase alphanumeric tokens."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return 0.0
        entry_tokens = self._tokenize(entry_text)
        if not entry_tokens:
            return 0.0
        return len(query_tokens & entry_tokens) / len(query_tokens | entry_tokens)

    def select_top_n(
        self,
        query: str,
        entries: list[MemoryEntry],
        n: int = 5,
    ) -> list[MemoryEntry]:
        """Return top scoring entries, preserving original order for ties."""
        if n <= 0:
            return []
        scored = [
            (
                self.score(query, self._entry_text(entry)),
                index,
                entry,
            )
            for index, entry in enumerate(entries)
        ]
        if not scored or all(score == 0.0 for score, _, _ in scored):
            return list(entries[:n])
        selected = sorted(scored, key=lambda item: (-item[0], item[1]))
        return [entry for _, _, entry in selected[:n]]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token.lower() for token in _MEMORY_TOKEN_PATTERN.findall(text)}

    @staticmethod
    def _entry_text(entry: MemoryEntry) -> str:
        return " ".join([entry.name, entry.body, *entry.tags])


_SESSION_MEMORY_VERSION = 1


class SessionMemory:
    """Ephemeral per-session memory; lives only in process memory."""

    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}

    def add(self, entry: MemoryEntry) -> None:
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        return self._entries.get(entry_id)

    def all(self) -> list[MemoryEntry]:
        return list(self._entries.values())

    def search(self, keyword: str) -> list[MemoryEntry]:
        """Case-insensitive substring search over name and body."""
        kw = keyword.lower()
        return [
            e for e in self._entries.values()
            if kw in e.name.lower() or kw in e.body.lower()
        ]

    def to_snippets(self) -> list[str]:
        """Format all entries for ContextBuilder.memory_snippets."""
        return [e.to_snippet() for e in self._entries.values()]

    def dump_json(self, path: str | Path) -> None:
        """Atomically persist all entries to `path` as JSON.

        Writes to a tempfile in the parent directory then `os.replace`s onto
        the target so a crash mid-dump leaves the previous snapshot intact.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _SESSION_MEMORY_VERSION,
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=target.name + ".",
            suffix=".tmp",
            dir=str(target.parent),
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp_name, str(target))
        except Exception:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
            raise

    @classmethod
    def load_json(cls, path: str | Path) -> SessionMemory:
        """Load a SessionMemory snapshot from disk.

        Missing file -> empty store.  Malformed JSON or non-conforming entries
        log a warning and yield an empty store; the caller never has to
        handle exceptions from this read path.
        """
        store = cls()
        target = Path(path)
        if not target.exists():
            return store
        try:
            with open(target, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (json.JSONDecodeError, OSError) as err:
            logger.warning(
                "session_memory: failed to parse JSON at %s: %s; "
                "returning empty store",
                target,
                err,
            )
            return store

        raw_entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(raw_entries, list):
            logger.warning(
                "session_memory: JSON at %s has no entries list; "
                "returning empty store",
                target,
            )
            return store

        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            try:
                entry = MemoryEntry.from_dict(raw)
            except (KeyError, ValueError) as err:
                logger.warning(
                    "session_memory: skipping malformed entry in %s: %s",
                    target,
                    err,
                )
                continue
            try:
                _check_body_for_secrets(entry.body)
            except ValueError as err:
                logger.warning(
                    "session_memory: skipping entry %r in %s due to "
                    "secret-like body: %s",
                    entry.id,
                    target,
                    err,
                )
                continue
            store.add(entry)
        return store


class ProjectMemory:
    """File-backed persistent memory for a project directory.

    Source: ~/.claude/projects/<slug>/memory/ in the Claude Code memory system.
    Each entry is a JSON file named {id}.json.
    MEMORY.md is maintained as a one-line-per-entry manifest.
    """

    def __init__(self, storage_dir: str) -> None:
        self._dir = str(Path(storage_dir).resolve())
        os.makedirs(self._dir, exist_ok=True)

    def save(self, entry: MemoryEntry) -> None:
        """Persist entry to disk.  Raises ValueError if body looks like a secret."""
        self._reject_secrets(entry.body)
        with open(self._entry_path(entry.id), "w", encoding="utf-8") as fh:
            json.dump(entry.to_dict(), fh, indent=2)
        self._update_manifest()

    def delete(self, entry_id: str) -> None:
        path = self._entry_path(entry_id)
        if os.path.exists(path):
            os.remove(path)
        self._update_manifest()

    def load(self, entry_id: str) -> MemoryEntry | None:
        path = self._entry_path(entry_id)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return MemoryEntry.from_dict(json.load(fh))

    def all(self) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for fname in os.listdir(self._dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(self._dir, fname), encoding="utf-8") as fh:
                    entries.append(MemoryEntry.from_dict(json.load(fh)))
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    def search(self, keyword: str) -> list[MemoryEntry]:
        kw = keyword.lower()
        return [
            e for e in self.all()
            if kw in e.name.lower() or kw in e.body.lower()
        ]

    def to_snippets(self, query: str | None = None) -> list[str]:
        entries = self.all()
        if query is not None:
            entries = MemorySelector().select_top_n(query, entries, n=5)
        return [e.to_snippet() for e in entries]

    def _update_manifest(self) -> None:
        """Rewrite MEMORY.md with one line per entry (<=200 lines per source)."""
        entries = self.all()
        lines: list[str] = ["# Memory Index\n"]
        for e in entries[:200]:
            preview = e.body[:_MAX_MANIFEST_BODY_PREVIEW].replace("\n", " ")
            safe_name = _escape_markdown_link_text(e.name)
            lines.append(f"- [{safe_name}]({e.id}.json) — {preview}\n")
        with open(os.path.join(self._dir, _MANIFEST_FILENAME), "w", encoding="utf-8") as fh:
            fh.writelines(lines)

    def _entry_path(self, entry_id: str) -> str:
        if not _SAFE_ENTRY_ID_PATTERN.fullmatch(entry_id):
            raise ValueError(f"invalid memory entry id: {entry_id!r}")

        root = Path(self._dir).resolve()
        path = (root / f"{entry_id}.json").resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"memory entry id escapes storage dir: {entry_id!r}")
        return str(path)

    @staticmethod
    def _reject_secrets(body: str) -> None:
        """Delegate to the module-level :func:`_check_body_for_secrets`.

        Kept for backwards compatibility with callers that referenced the
        static method directly.
        """
        _check_body_for_secrets(body)
