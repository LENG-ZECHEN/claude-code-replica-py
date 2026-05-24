"""Tests for memdir.format_memory_manifest."""
from __future__ import annotations

from pathlib import Path


def _make_header(id: str, name: str, description: str | None, tmp_path: Path):
    from simple_coding_agent.memory import MemoryHeader

    fake_path = tmp_path / f"{id}.md"
    return MemoryHeader(
        id=id,
        name=name,
        type="user",
        description=description,
        path=fake_path,
        mtime=0.0,
    )


def test_format_manifest_basic(tmp_path: Path) -> None:
    from simple_coding_agent.memdir import format_memory_manifest

    headers = [
        _make_header("user_role", "User Role", "The user's role", tmp_path),
        _make_header("feedback_testing", "Testing feedback", "Avoid mocks", tmp_path),
    ]
    manifest = format_memory_manifest(headers)
    assert "- [User Role](user_role.md) — The user's role" in manifest
    assert "- [Testing feedback](feedback_testing.md) — Avoid mocks" in manifest
    assert manifest.count("- [") == 2


def test_format_manifest_no_description(tmp_path: Path) -> None:
    from simple_coding_agent.memdir import format_memory_manifest

    headers = [_make_header("bare_entry", "Bare Entry", None, tmp_path)]
    manifest = format_memory_manifest(headers)
    assert "- [Bare Entry](bare_entry.md)" in manifest
    assert " — " not in manifest


def test_format_manifest_truncates_at_200_entries(tmp_path: Path) -> None:
    from simple_coding_agent.memdir import format_memory_manifest

    headers = [
        _make_header(f"entry_{i}", f"Entry {i}", f"desc {i}", tmp_path)
        for i in range(201)
    ]
    manifest = format_memory_manifest(headers)
    # Only 200 entries rendered
    assert manifest.count("- [") == 200
    # Warning footer present
    assert "WARNING" in manifest or "truncated" in manifest.lower()
