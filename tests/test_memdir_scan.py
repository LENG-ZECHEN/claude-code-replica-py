"""Tests for memdir.scan_memory_files (re-exported from memdir.py)."""
from __future__ import annotations

import time
from pathlib import Path


def test_scan_returns_memory_headers_sorted_by_mtime(tmp_path: Path) -> None:
    from simple_coding_agent.memdir import scan_memory_files

    older = tmp_path / "older.md"
    older.write_text(
        "---\nname: Older\ntype: user\ndescription: old\ncreated_at: 2026-01-01\n---\n\nbody\n"
    )
    time.sleep(0.01)
    newer = tmp_path / "newer.md"
    newer.write_text(
        "---\nname: Newer\ntype: feedback\ndescription: new\ncreated_at: 2026-01-02\n---\n\nbody\n"
    )

    headers = scan_memory_files(tmp_path)
    assert len(headers) == 2
    assert headers[0].name == "Newer"
    assert headers[1].name == "Older"


def test_scan_excludes_memory_md(tmp_path: Path) -> None:
    from simple_coding_agent.memdir import scan_memory_files

    memory_md = tmp_path / "MEMORY.md"
    memory_md.write_text("# Memory Index\n- [foo](foo.md) — a foo\n")

    regular = tmp_path / "note.md"
    regular.write_text(
        "---\nname: Note\ntype: project\ndescription: a note\ncreated_at: 2026-01-01\n---\n\nbody\n"
    )

    headers = scan_memory_files(tmp_path)
    names = [h.name for h in headers]
    assert "Note" in names
    assert not any(h.path.name == "MEMORY.md" for h in headers)
