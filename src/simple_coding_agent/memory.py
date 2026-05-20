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
import os
import re
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

_MANIFEST_FILENAME = "MEMORY.md"
_MAX_MANIFEST_BODY_PREVIEW = 80
_SAFE_ENTRY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key)\s*[=:]\s*\S+",
)
_MEMORY_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


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
            lines.append(f"- [{e.name}]({e.id}.json) — {preview}\n")
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
        if _SECRET_PATTERN.search(body):
            raise ValueError(
                "Memory body appears to contain a secret (key=value pattern). "
                "Do not store secrets in memory."
            )
