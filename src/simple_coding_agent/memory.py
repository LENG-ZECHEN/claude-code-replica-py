"""
MemoryStore: session-scoped and project-scoped memory with file-backed persistence.

Source mapping:
  MemoryEntry    <- memory file format in ~/.claude/projects/<slug>/memory/
  MemoryType     <- user/feedback/project/reference types from CLAUDE.md memory system
  MemoryHeader   <- lightweight scan result (frontmatter only, no body)
  SessionMemory  <- in-process ephemeral memory (lost when process exits)
  ProjectMemory  <- file-backed persistent memory (~/.claude/projects/<slug>/memory/)
  MEMORY.md      <- manifest index (<=200 lines per source constraint)
  scan_memory_files() <- recursively scans .md files, returns MemoryHeader[]
  to_snippets()  <- memory injection format consumed by ContextBuilder.memory_snippets

Security: save() rejects body text that looks like a secret assignment
(e.g. API_KEY=..., TOKEN=...) to prevent accidental secret persistence.

M1 (auto-memory-overhaul): ProjectMemory now writes .md files with YAML
frontmatter (name/type/description/created_at). Legacy .json entries are
read during the compat window until migrate-format is run.
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

from .trace import NullTracer, Tracer

logger = logging.getLogger(__name__)

_MANIFEST_FILENAME = "MEMORY.md"
_MAX_MANIFEST_BODY_PREVIEW = 80
_MANIFEST_MAX_LINES = 200
_MANIFEST_MAX_BYTES = 25_000
FRONTMATTER_MAX_LINES = 30

# Allows plain IDs (legacy) and /‑separated subdir IDs (e.g. "user/role").
# Dots are intentionally excluded so ".." can never appear as a segment.
_SAFE_ENTRY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-/]{0,127}$")

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


# ---------------------------------------------------------------------------
# Secret / markdown helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Frontmatter parsing helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(lines: list[str]) -> dict[str, str]:
    """Parse YAML-like frontmatter from a list of file lines (no newlines).

    Returns a dict of key→value when valid frontmatter is found (opening
    ``---``, closing ``---`` within FRONTMATTER_MAX_LINES, simple key: value
    pairs).  Returns ``{}`` on any failure — callers always get a safe default.
    """
    if not lines or lines[0].rstrip("\n\r") != "---":
        return {}
    result: dict[str, str] = {}
    for i in range(1, min(FRONTMATTER_MAX_LINES + 1, len(lines))):
        stripped = lines[i].rstrip("\n\r")
        if stripped == "---":
            return result
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if key and not key.startswith(" "):
                result[key] = value
    return {}  # no closing --- within FRONTMATTER_MAX_LINES lines


def _read_first_lines(path: Path, n: int) -> list[str]:
    """Read the first *n* lines from *path*; return [] on OSError."""
    lines: list[str] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for _ in range(n):
                line = fh.readline()
                if not line:
                    break
                lines.append(line)
    except OSError:
        pass
    return lines


# ---------------------------------------------------------------------------
# Core types: MemoryType, MemoryEntry
# ---------------------------------------------------------------------------

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
    """
    name: str
    body: str
    type: MemoryType
    id: str = field(default_factory=lambda: str(_uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    tags: list[str] = field(default_factory=list)
    description: str | None = field(default=None)

    def _effective_description(self) -> str:
        """One-line description for frontmatter: explicit value or body preview."""
        if self.description:
            return self.description
        return self.body.split("\n")[0][:150]

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

    def to_md_text(self) -> str:
        """Serialize to .md format with YAML frontmatter."""
        # Sanitize multi-line values that would break frontmatter parsing.
        safe_name = self.name.replace("\n", " ").replace("\r", " ")
        desc = self._effective_description().replace("\n", " ").replace("\r", " ")
        parts = [
            "---",
            f"name: {safe_name}",
            f"type: {self.type.value}",
            f"description: {desc}",
            f"created_at: {self.created_at}",
            "---",
            "",
            self.body,
        ]
        return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# MemoryHeader and scan_memory_files
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryHeader:
    """Lightweight scan result — frontmatter only, body not loaded.

    Source: MemoryHeader in claude-code-source-code/src/memdir/memoryScan.ts
    """
    id: str                  # relative path without .md suffix, e.g. "user/role"
    name: str                # from frontmatter name: or "" if missing / unparseable
    type: str | None         # "user"|"feedback"|"project"|"reference" or None
    description: str | None  # one-line summary, or None if frontmatter parse failed
    path: Path               # absolute path to .md file
    mtime: float             # os.stat st_mtime


def scan_memory_files(directory: Path) -> list[MemoryHeader]:
    """Recursively scan *directory* for .md memory files.

    Returns ``MemoryHeader[]`` sorted by mtime descending (newest first).
    Excludes MEMORY.md by basename.  Skips any resolved path outside directory.
    """
    resolved = directory.resolve()
    headers: list[MemoryHeader] = []
    for md_path in resolved.glob("**/*.md"):
        if md_path.name == _MANIFEST_FILENAME:
            continue
        if not md_path.is_relative_to(resolved):
            continue
        try:
            mtime = md_path.stat().st_mtime
        except OSError:
            continue
        rel = md_path.relative_to(resolved)
        entry_id = str(rel.with_suffix(""))
        lines = _read_first_lines(md_path, FRONTMATTER_MAX_LINES + 2)
        fm = _parse_frontmatter([ln.rstrip("\n\r") for ln in lines])
        name = fm.get("name", "")
        raw_desc = fm.get("description")
        description: str | None = raw_desc if raw_desc else None
        mem_type: str | None = fm.get("type") or None
        headers.append(MemoryHeader(
            id=entry_id,
            name=name,
            type=mem_type,
            description=description,
            path=md_path,
            mtime=mtime,
        ))
    headers.sort(key=lambda h: h.mtime, reverse=True)
    return headers


# ---------------------------------------------------------------------------
# .md file parser (body + frontmatter → MemoryEntry)
# ---------------------------------------------------------------------------

def _parse_entry_md(text: str, entry_id: str) -> MemoryEntry | None:
    """Parse a .md file (YAML frontmatter + body) into a MemoryEntry.

    Returns a MemoryEntry even when frontmatter is malformed (uses entry_id
    as name, empty body).  Returns None only on unexpected exceptions.
    """
    try:
        raw_lines = text.splitlines(keepends=True)
        stripped = [ln.rstrip("\n\r") for ln in raw_lines[:FRONTMATTER_MAX_LINES + 2]]
        fm = _parse_frontmatter(stripped)
        # Locate body: first line after the closing ---
        body_start = 0
        if raw_lines and raw_lines[0].rstrip("\n\r") == "---":
            for i in range(1, min(FRONTMATTER_MAX_LINES + 2, len(raw_lines))):
                if raw_lines[i].rstrip("\n\r") == "---":
                    body_start = i + 1
                    break
        body_lines = raw_lines[body_start:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        body = "".join(body_lines).rstrip()
        name = fm.get("name", entry_id)
        type_str = fm.get("type", "project")
        try:
            mem_type = MemoryType(type_str)
        except ValueError:
            mem_type = MemoryType.PROJECT
        return MemoryEntry(
            id=entry_id,
            name=name,
            body=body,
            type=mem_type,
            description=fm.get("description") or None,
            created_at=fm.get("created_at", datetime.now(UTC).isoformat()),
        )
    except Exception as err:
        logger.warning("memory: _parse_entry_md failed for %r: %s", entry_id, err)
        return None


# ---------------------------------------------------------------------------
# MemorySelector
# ---------------------------------------------------------------------------

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
            (self.score(query, self._entry_text(entry)), index, entry)
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


# ---------------------------------------------------------------------------
# SessionMemory
# ---------------------------------------------------------------------------

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
        """Atomically persist all entries to *path* as JSON."""
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

        Missing file → empty store.  Malformed JSON or non-conforming entries
        log a warning and yield an empty store.
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


# ---------------------------------------------------------------------------
# ProjectMemory
# ---------------------------------------------------------------------------

class ProjectMemory:
    """File-backed persistent memory for a project directory.

    Source: ~/.claude/projects/<slug>/memory/ in the Claude Code memory system.
    Each entry is a .md file with YAML frontmatter.
    MEMORY.md is maintained as a one-line-per-entry manifest (<=200 lines).
    Legacy .json entries are read during the migration compat window.
    """

    def __init__(
        self,
        storage_dir: str,
        *,
        tracer: Tracer | None = None,
    ) -> None:
        self._dir = str(Path(storage_dir).resolve())
        os.makedirs(self._dir, exist_ok=True)
        self._tracer: Tracer = tracer or NullTracer()

    def save(self, entry: MemoryEntry) -> None:
        """Persist entry to disk as .md with YAML frontmatter."""
        self._reject_secrets(entry.body)
        path = self._entry_path_md(entry.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.to_md_text(), encoding="utf-8")
        self._update_manifest()

    def delete(self, entry_id: str) -> None:
        """Remove a memory entry by ID (handles both .md and legacy .json)."""
        md_path = self._entry_path_md(entry_id)
        json_path = self._entry_path_json_legacy(entry_id)
        removed = False
        if md_path.exists():
            md_path.unlink()
            removed = True
        if json_path.exists():
            json_path.unlink()
            removed = True
        if removed:
            self._update_manifest()
        # Idempotent: no-op if neither file existed.

    def load(self, entry_id: str) -> MemoryEntry | None:
        """Load one entry by ID. Tries .md first, then legacy .json."""
        md_path = self._entry_path_md(entry_id)
        if md_path.exists():
            try:
                return _parse_entry_md(md_path.read_text(encoding="utf-8"), entry_id)
            except Exception as err:
                logger.warning("memory: failed to parse %s: %s", md_path, err)
        json_path = self._entry_path_json_legacy(entry_id)
        if json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as fh:
                    return MemoryEntry.from_dict(json.load(fh))
            except (json.JSONDecodeError, KeyError):
                return None
        return None

    def all(self) -> list[MemoryEntry]:
        """Return all entries: .md files (canonical) + legacy .json files."""
        entries, seen_ids = self._load_all_md_entries()
        entries.extend(self._load_legacy_json_entries(seen_ids))
        return entries

    def search(self, keyword: str) -> list[MemoryEntry]:
        kw = keyword.lower()
        return [
            e for e in self.all()
            if kw in e.name.lower() or kw in e.body.lower()
        ]

    def to_snippets(self, query: str | None = None) -> list[str]:
        entries = self.all()
        total = len(entries)
        if query is not None:
            entries = MemorySelector().select_top_n(query, entries, n=5)
            self._tracer.emit(
                "memory_select",
                selected=len(entries),
                total=total,
            )
        return [e.to_snippet() for e in entries]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_entry_path(self, entry_id: str, suffix: str) -> Path:
        if not _SAFE_ENTRY_ID_PATTERN.fullmatch(entry_id):
            raise ValueError(f"invalid memory entry id: {entry_id!r}")
        root = Path(self._dir).resolve()
        path = (root / f"{entry_id}{suffix}").resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"memory entry id escapes storage dir: {entry_id!r}")
        return path

    def _entry_path_md(self, entry_id: str) -> Path:
        return self._resolve_entry_path(entry_id, ".md")

    def _entry_path_json_legacy(self, entry_id: str) -> Path:
        return self._resolve_entry_path(entry_id, ".json")

    def _load_all_md_entries(self) -> tuple[list[MemoryEntry], set[str]]:
        entries: list[MemoryEntry] = []
        seen_ids: set[str] = set()
        dir_path = Path(self._dir)
        for md_path in dir_path.glob("**/*.md"):
            if md_path.name == _MANIFEST_FILENAME:
                continue
            if not md_path.resolve().is_relative_to(dir_path.resolve()):
                continue
            rel = md_path.relative_to(dir_path)
            entry_id = str(rel.with_suffix(""))
            try:
                entry = _parse_entry_md(md_path.read_text(encoding="utf-8"), entry_id)
                if entry is not None:
                    entries.append(entry)
                    seen_ids.add(entry_id)
            except Exception:
                continue
        return entries, seen_ids

    def _load_legacy_json_entries(self, skip_ids: set[str]) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for fname in os.listdir(self._dir):
            if not fname.endswith(".json"):
                continue
            entry_id = fname[:-5]
            if entry_id in skip_ids:
                continue
            try:
                with open(os.path.join(self._dir, fname), encoding="utf-8") as fh:
                    entries.append(MemoryEntry.from_dict(json.load(fh)))
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    def _update_manifest(self) -> None:
        """Atomically rewrite MEMORY.md with the current entry index."""
        headers = scan_memory_files(Path(self._dir))
        content = self._build_manifest_content(headers)
        target = Path(self._dir) / _MANIFEST_FILENAME
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=_MANIFEST_FILENAME + ".",
            suffix=".tmp",
            dir=self._dir,
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp_name, str(target))
        except Exception:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
            raise

    def _build_manifest_content(self, headers: list[MemoryHeader]) -> str:
        """Build MEMORY.md content with 200-line and 25 KB truncation."""
        dir_path = Path(self._dir)
        total = len(headers)
        lines: list[str] = []
        for h in headers[:_MANIFEST_MAX_LINES]:
            rel = h.path.relative_to(dir_path)
            safe_name = _escape_markdown_link_text(h.name or h.id)
            desc = h.description or "(no description)"
            lines.append(f"- [{safe_name}]({rel}) — {desc}")
        content = "\n".join(lines)
        line_truncated = total > len(lines)
        byte_truncated = False
        if len(content.encode("utf-8")) > _MANIFEST_MAX_BYTES:
            byte_truncated = True
            cut_at = content.rfind("\n", 0, _MANIFEST_MAX_BYTES)
            content = content[:cut_at] if cut_at > 0 else content[:_MANIFEST_MAX_BYTES]
        if line_truncated or byte_truncated:
            included = content.count("\n") + 1 if content.strip() else 0
            omitted = max(0, total - included)
            content += f"\n\n> [truncated — {omitted} entries omitted to stay within limits]"
        return content + "\n"

    @staticmethod
    def _reject_secrets(body: str) -> None:
        """Delegate to the module-level :func:`_check_body_for_secrets`."""
        _check_body_for_secrets(body)
