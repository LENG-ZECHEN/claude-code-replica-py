"""M1 / A1: Manifest format and truncation tests (TDD — write before implementation)."""

from __future__ import annotations

from pathlib import Path

from simple_coding_agent.memory import MemoryEntry, MemoryType, ProjectMemory


def test_manifest_basic_format(tmp_path: Path) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="my-fact", body="body content", type=MemoryType.USER))
    manifest = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    # Should have at least one line matching the expected format
    lines = [ln for ln in manifest.splitlines() if ln.startswith("- [")]
    assert lines, "No manifest entry lines found"
    line = lines[0]
    assert "my-fact" in line
    assert "](" in line
    assert ".md)" in line
    assert " — " in line


def test_manifest_200_line_truncation(tmp_path: Path) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    for i in range(250):
        pm.save(MemoryEntry(
            id=f"entry{i:03d}",
            name=f"entry-{i}",
            body=f"body {i}",
            type=MemoryType.PROJECT,
        ))
    manifest = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    lines = manifest.splitlines()
    # Should be truncated with a warning footer
    assert any("truncated" in ln.lower() or "omitted" in ln.lower() for ln in lines), (
        "Missing truncation warning footer"
    )
    entry_lines = [ln for ln in lines if ln.startswith("- [")]
    # At most 200 entry lines
    assert len(entry_lines) <= 200


def test_manifest_25kb_truncation(tmp_path: Path) -> None:
    # Create entries with very long descriptions to exceed 25KB
    pm = ProjectMemory(storage_dir=str(tmp_path))
    long_desc = "x" * 200
    for i in range(150):
        pm.save(MemoryEntry(
            id=f"long{i:03d}",
            name=f"long-entry-{i}",
            body=long_desc,
            type=MemoryType.PROJECT,
        ))
    manifest = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert len(manifest.encode("utf-8")) <= 26_000  # allow small overhead for footer
    # Truncation warning must appear
    assert "truncated" in manifest.lower() or "omitted" in manifest.lower()


def test_manifest_excludes_memory_md(tmp_path: Path) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="real-entry", body="some body", type=MemoryType.USER))
    manifest = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    # MEMORY.md itself must not appear as a link target in the manifest
    assert "MEMORY.md" not in manifest or not any(
        "MEMORY.md" in ln for ln in manifest.splitlines() if ln.startswith("- [")
    )
