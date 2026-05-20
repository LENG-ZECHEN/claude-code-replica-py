"""P6: ClaudeMdLoader tests — written before implementation (TDD)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from simple_coding_agent.claude_md import ClaudeMdLoader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loader(user_path: Path | None = None) -> ClaudeMdLoader:
    """Create a loader with a controlled user_claude_path so tests never read
    the real ~/.claude/CLAUDE.md."""
    return ClaudeMdLoader(user_claude_path=user_path)


# ---------------------------------------------------------------------------
# 1. Empty result when no files exist
# ---------------------------------------------------------------------------

def test_load_returns_empty_when_no_files_exist(tmp_path: Path) -> None:
    nonexistent_user = tmp_path / "no_user_claude.md"
    loader = _loader(user_path=nonexistent_user)
    result = loader.load(tmp_path)
    assert result == ""


# ---------------------------------------------------------------------------
# 2. Project-level CLAUDE.md
# ---------------------------------------------------------------------------

def test_load_returns_project_claude_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# Project rules\nBe concise.", encoding="utf-8")
    loader = _loader(user_path=tmp_path / "nonexistent.md")
    result = loader.load(tmp_path)
    assert result == "# Project rules\nBe concise."


# ---------------------------------------------------------------------------
# 3. User-level CLAUDE.md
# ---------------------------------------------------------------------------

def test_load_returns_user_claude_md(tmp_path: Path) -> None:
    user_file = tmp_path / "user_claude.md"
    user_file.write_text("User preference: no emojis.", encoding="utf-8")
    loader = _loader(user_path=user_file)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = loader.load(workspace)
    assert result == "User preference: no emojis."


# ---------------------------------------------------------------------------
# 4. Both files: project content first, then user content
# ---------------------------------------------------------------------------

def test_load_project_before_user_when_both_exist(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "CLAUDE.md").write_text("project content", encoding="utf-8")
    user_file = tmp_path / "user_claude.md"
    user_file.write_text("user content", encoding="utf-8")
    loader = _loader(user_path=user_file)
    result = loader.load(workspace)
    assert result == "project content\n\nuser content"
    assert result.index("project content") < result.index("user content")


# ---------------------------------------------------------------------------
# 5. Read errors are caught — no crash
# ---------------------------------------------------------------------------

def test_load_catches_project_read_error(tmp_path: Path) -> None:
    project_file = tmp_path / "CLAUDE.md"
    project_file.write_text("should not appear", encoding="utf-8")
    loader = _loader(user_path=tmp_path / "no_user.md")
    with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
        result = loader.load(tmp_path)
    assert result == ""


def test_load_catches_user_read_error(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "CLAUDE.md").write_text("project ok", encoding="utf-8")
    user_file = tmp_path / "user.md"
    user_file.write_text("user ok", encoding="utf-8")

    original_read_text = Path.read_text

    def _selective_raise(self: Path, **kwargs: object) -> str:
        if self == user_file:
            raise OSError("no permission")
        return original_read_text(self, **kwargs)  # type: ignore[arg-type]

    loader = _loader(user_path=user_file)
    with patch.object(Path, "read_text", _selective_raise):
        result = loader.load(workspace)
    assert result == "project ok"


# ---------------------------------------------------------------------------
# 6. Caching: second call returns original content even after file change
# ---------------------------------------------------------------------------

def test_load_caches_result(tmp_path: Path) -> None:
    project_file = tmp_path / "CLAUDE.md"
    project_file.write_text("original content", encoding="utf-8")
    loader = _loader(user_path=tmp_path / "no_user.md")

    first = loader.load(tmp_path)
    assert first == "original content"

    project_file.write_text("modified content", encoding="utf-8")

    second = loader.load(tmp_path)
    assert second == "original content"  # cached — file not re-read


def test_load_cache_is_per_workspace(tmp_path: Path) -> None:
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    (ws1 / "CLAUDE.md").write_text("ws1 rules", encoding="utf-8")
    (ws2 / "CLAUDE.md").write_text("ws2 rules", encoding="utf-8")
    loader = _loader(user_path=tmp_path / "no_user.md")

    assert loader.load(ws1) == "ws1 rules"
    assert loader.load(ws2) == "ws2 rules"


def test_load_does_not_cache_on_read_error(tmp_path: Path) -> None:
    """A transient OSError must not freeze an empty string in the cache."""
    project_file = tmp_path / "CLAUDE.md"
    project_file.write_text("real content", encoding="utf-8")
    loader = _loader(user_path=tmp_path / "no_user.md")

    with patch.object(Path, "read_text", side_effect=OSError("transient")):
        error_result = loader.load(tmp_path)
    assert error_result == ""

    # After the error is gone the file should be re-read successfully
    second = loader.load(tmp_path)
    assert second == "real content"
