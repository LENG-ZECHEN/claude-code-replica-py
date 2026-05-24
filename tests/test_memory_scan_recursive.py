"""M1 / A1: Recursive scan tests (TDD — write before implementation)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from simple_coding_agent.memory import scan_memory_files


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


_BASIC_FM = "---\nname: {name}\ntype: user\ndescription: desc\ncreated_at: 2026-01-01\n---\n\nBody."


def test_scan_finds_subdirectory_entries(tmp_path: Path) -> None:
    _write_md(tmp_path / "user" / "role.md", _BASIC_FM.format(name="user-role"))
    _write_md(tmp_path / "feedback" / "testing.md", _BASIC_FM.format(name="feedback-testing"))
    _write_md(tmp_path / "top_level.md", _BASIC_FM.format(name="top-level"))
    headers = scan_memory_files(tmp_path)
    ids = {h.id for h in headers}
    assert "user/role" in ids
    assert "feedback/testing" in ids
    assert "top_level" in ids


def test_scan_mtime_order(tmp_path: Path) -> None:
    older = tmp_path / "older.md"
    newer = tmp_path / "newer.md"
    _write_md(older, _BASIC_FM.format(name="older"))
    # Force distinct mtime by advancing os.utime
    os.utime(older, (time.time() - 5, time.time() - 5))
    _write_md(newer, _BASIC_FM.format(name="newer"))
    headers = scan_memory_files(tmp_path)
    assert len(headers) == 2
    # newest first
    assert headers[0].name == "newer"
    assert headers[1].name == "older"


def test_scan_excludes_memory_md(tmp_path: Path) -> None:
    _write_md(tmp_path / "entry.md", _BASIC_FM.format(name="entry"))
    # Create a MEMORY.md — it must be excluded from scan results
    (tmp_path / "MEMORY.md").write_text("# Memory Index\n\n- [entry](entry.md) — desc\n")
    headers = scan_memory_files(tmp_path)
    ids = {h.id for h in headers}
    assert "MEMORY" not in ids
    assert "entry" in ids
