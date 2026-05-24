"""M1 / A1: Frontmatter parsing tests (TDD — write before implementation)."""

from __future__ import annotations

from pathlib import Path

from simple_coding_agent.memory import scan_memory_files


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_tags_round_trip_through_md(tmp_path: Path) -> None:
    """tags must survive save (to_md_text) -> load (_parse_entry_md).

    Regression for the auto-memory-overhaul review finding where to_md_text
    silently dropped the tags field even though MemoryEntry/to_dict carried it.
    """
    from simple_coding_agent.memory import MemoryEntry, MemoryType, ProjectMemory

    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(
        MemoryEntry(
            id="tagged",
            name="Tagged entry",
            body="some body",
            type=MemoryType.USER,
            tags=["alpha", "beta-two"],
        )
    )
    raw = (tmp_path / "tagged.md").read_text(encoding="utf-8")
    assert "tags:" in raw  # frontmatter on disk carries the tags line

    loaded = pm.load("tagged")
    assert loaded is not None
    assert loaded.tags == ["alpha", "beta-two"]


def test_no_tags_line_when_empty(tmp_path: Path) -> None:
    """Entries without tags must not emit an empty `tags:` frontmatter line."""
    from simple_coding_agent.memory import MemoryEntry, MemoryType, ProjectMemory

    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(id="plain", name="Plain", body="b", type=MemoryType.USER))
    raw = (tmp_path / "plain.md").read_text(encoding="utf-8")
    assert "tags:" not in raw

    loaded = pm.load("plain")
    assert loaded is not None
    assert loaded.tags == []


def test_parse_valid_frontmatter(tmp_path: Path) -> None:
    _write_md(
        tmp_path / "user_role.md",
        "---\nname: user-role\ntype: user\ndescription: Senior Python engineer\n"
        "created_at: 2026-01-01T00:00:00\n---\n\nBody here.",
    )
    headers = scan_memory_files(tmp_path)
    assert len(headers) == 1
    h = headers[0]
    assert h.name == "user-role"
    assert h.type == "user"
    assert h.description == "Senior Python engineer"
    assert h.id == "user_role"


def test_parse_missing_description(tmp_path: Path) -> None:
    _write_md(
        tmp_path / "feedback_test.md",
        "---\nname: feedback-test\ntype: feedback\ncreated_at: 2026-01-01\n---\n\nBody.",
    )
    headers = scan_memory_files(tmp_path)
    assert len(headers) == 1
    assert headers[0].description is None


def test_parse_no_closing_delimiter(tmp_path: Path) -> None:
    # More than 30 lines without a closing ---
    lines = ["---\n"] + [f"key{i}: value{i}\n" for i in range(32)]
    _write_md(tmp_path / "overlong.md", "".join(lines))
    headers = scan_memory_files(tmp_path)
    assert len(headers) == 1
    assert headers[0].description is None
    # File is still usable by ID
    assert headers[0].id == "overlong"


def test_parse_torn_frontmatter(tmp_path: Path) -> None:
    # Frontmatter with a key but no value (malformed line — no colon)
    _write_md(
        tmp_path / "torn.md",
        "---\nname_without_colon\ntype: project\n---\n\nBody.",
    )
    headers = scan_memory_files(tmp_path)
    assert len(headers) == 1
    # name: is absent so name defaults to ""
    # The description key is missing too
    assert headers[0].description is None
    assert headers[0].id == "torn"
