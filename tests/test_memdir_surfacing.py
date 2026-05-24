"""Tests for memdir.read_memories_for_surfacing — truncation + staleness header."""
from __future__ import annotations

import time
from pathlib import Path

from simple_coding_agent.memdir import read_memories_for_surfacing
from simple_coding_agent.memory import MemoryHeader

# ---------------------------------------------------------------------------
# Helper: build a MemoryHeader with a real temp file
# ---------------------------------------------------------------------------


def _make_header(
    directory: Path,
    entry_id: str,
    content: str,
    mtime_offset_seconds: float = 0.0,
) -> MemoryHeader:
    """Write *content* to a .md file and return a MemoryHeader for it."""
    file_path = directory / f"{entry_id}.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    mtime = time.time() - mtime_offset_seconds
    return MemoryHeader(
        id=entry_id,
        name="Test Memory",
        type="user",
        description="A test memory",
        path=file_path,
        mtime=mtime,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReadMemoriesForSurfacing:
    def test_reads_up_to_200_lines(self, tmp_path: Path) -> None:
        content = "\n".join(f"line {i}" for i in range(250)) + "\n"
        header = _make_header(tmp_path, "big_mem", content)
        results = read_memories_for_surfacing([header])
        assert len(results) == 1
        text = results[0]
        lines = text.split("\n")
        # Header line + 200 content lines + truncation warning = 202 lines
        # (allow for staleness header on first line)
        content_lines = [
            ln for ln in lines
            if ln.startswith("line ")
        ]
        assert len(content_lines) == 200

    def test_truncation_warning_appended(self, tmp_path: Path) -> None:
        content = "\n".join(f"line {i}" for i in range(250)) + "\n"
        header = _make_header(tmp_path, "big_mem", content)
        results = read_memories_for_surfacing([header])
        assert len(results) == 1
        text = results[0]
        assert "[...truncated" in text
        assert "lines omitted]" in text

    def test_truncation_4kb_limit(self, tmp_path: Path) -> None:
        # Each line is 100 chars; 50 lines = 5000 bytes > 4096 bytes
        line = "x" * 99  # 99 chars + newline = 100 bytes
        content = "\n".join([line] * 60) + "\n"
        header = _make_header(tmp_path, "big_mem", content)
        results = read_memories_for_surfacing([header])
        assert len(results) == 1
        text = results[0]
        # Should be truncated (content > 4KB)
        assert "[...truncated" in text

    def test_short_content_not_truncated(self, tmp_path: Path) -> None:
        content = "---\nname: Short\n---\n\nShort body.\n"
        header = _make_header(tmp_path, "short_mem", content)
        results = read_memories_for_surfacing([header])
        assert len(results) == 1
        assert "[...truncated" not in results[0]
        assert "Short body." in results[0]

    def test_staleness_header_today(self, tmp_path: Path) -> None:
        content = "Body\n"
        header = _make_header(tmp_path, "new_mem", content, mtime_offset_seconds=30)
        results = read_memories_for_surfacing([header])
        assert len(results) == 1
        assert "saved today" in results[0]

    def test_staleness_header_days_ago(self, tmp_path: Path) -> None:
        content = "Body\n"
        # 3 days ago = 3 * 86400 seconds
        header = _make_header(
            tmp_path, "old_mem", content, mtime_offset_seconds=3 * 86400 + 60
        )
        results = read_memories_for_surfacing([header])
        assert len(results) == 1
        assert "3 days ago" in results[0]

    def test_multiple_files_returned(self, tmp_path: Path) -> None:
        h1 = _make_header(tmp_path, "mem_a", "Content A\n")
        h2 = _make_header(tmp_path, "mem_b", "Content B\n")
        results = read_memories_for_surfacing([h1, h2])
        assert len(results) == 2
        assert any("Content A" in r for r in results)
        assert any("Content B" in r for r in results)

    def test_missing_file_returns_placeholder(self, tmp_path: Path) -> None:
        header = MemoryHeader(
            id="gone",
            name="Gone",
            type="user",
            description=None,
            path=tmp_path / "gone.md",  # does not exist
            mtime=time.time(),
        )
        results = read_memories_for_surfacing([header])
        assert len(results) == 1
        # Should not raise; returns some text
        assert isinstance(results[0], str)

    def test_empty_selected_returns_empty(self, tmp_path: Path) -> None:
        results = read_memories_for_surfacing([])
        assert results == []
