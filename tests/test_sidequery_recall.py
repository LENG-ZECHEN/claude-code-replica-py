"""Tests for memdir.find_relevant_memories — 4-gate guard + selector + Jaccard fallback."""
from __future__ import annotations

from pathlib import Path

from simple_coding_agent.memdir import find_relevant_memories
from simple_coding_agent.provider import MockProvider

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_memory(
    directory: Path,
    entry_id: str,
    name: str = "test",
    desc: str = "test description",
) -> None:
    """Write a minimal memory .md file."""
    file_path = directory / f"{entry_id}.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        f"---\nname: {name}\ntype: user\n"
        f"description: {desc}\ncreated_at: 2026-01-01T00:00:00+00:00\n---\n\nBody text.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Gate tests
# ---------------------------------------------------------------------------


class TestFindRelevantMemoriesGates:
    def test_gate_empty_query_returns_empty(self, tmp_path: Path) -> None:
        _write_memory(tmp_path, "user/role", name="My role", desc="Developer")
        provider = MockProvider(
            [], selector_responses=[{"filenames": ["user/role.md"]}]
        )
        result = find_relevant_memories(
            "", tmp_path, provider,
            already_surfaced=set(),
            recent_tools=[], session_bytes_used=0,
            auto_memory_enabled=True,
        )
        assert result.headers == []

    def test_gate_single_word_query_returns_empty(self, tmp_path: Path) -> None:
        _write_memory(tmp_path, "user/role", name="My role", desc="Developer")
        provider = MockProvider(
            [], selector_responses=[{"filenames": ["user/role.md"]}]
        )
        result = find_relevant_memories(
            "hello", tmp_path, provider,
            already_surfaced=set(),
            recent_tools=[], session_bytes_used=0,
            auto_memory_enabled=True,
        )
        assert result.headers == []

    def test_gate_session_bytes_ceiling_returns_empty(self, tmp_path: Path) -> None:
        _write_memory(tmp_path, "user/role", name="My role", desc="Developer")
        provider = MockProvider(
            [], selector_responses=[{"filenames": ["user/role.md"]}]
        )
        result = find_relevant_memories(
            "what is my role", tmp_path, provider,
            already_surfaced=set(),
            recent_tools=[], session_bytes_used=61 * 1024,  # > 60KB ceiling
            auto_memory_enabled=True,
        )
        assert result.headers == []

    def test_gate_auto_memory_disabled_returns_empty(self, tmp_path: Path) -> None:
        _write_memory(tmp_path, "user/role", name="My role", desc="Developer")
        provider = MockProvider(
            [], selector_responses=[{"filenames": ["user/role.md"]}]
        )
        result = find_relevant_memories(
            "what is my role", tmp_path, provider,
            already_surfaced=set(),
            recent_tools=[], session_bytes_used=0,
            auto_memory_enabled=False,
        )
        assert result.headers == []


# ---------------------------------------------------------------------------
# Selector / manifest tests
# ---------------------------------------------------------------------------


class TestFindRelevantMemoriesSelector:
    def test_valid_query_calls_selector(self, tmp_path: Path) -> None:
        _write_memory(tmp_path, "user/role", name="User role", desc="coding role")
        provider = MockProvider(
            [], selector_responses=[{"filenames": ["user/role.md"]}]
        )
        result = find_relevant_memories(
            "what is my role", tmp_path, provider,
            already_surfaced=set(),
            recent_tools=[], session_bytes_used=0,
            auto_memory_enabled=True,
        )
        assert len(result.headers) == 1
        assert result.headers[0].id == "user/role"

    def test_hallucinated_filename_dropped(self, tmp_path: Path) -> None:
        _write_memory(tmp_path, "user/role", name="User role", desc="coding role")
        # Selector returns a filename that doesn't exist in the manifest
        provider = MockProvider(
            [],
            selector_responses=[
                {"filenames": ["user/role.md", "nonexistent/memory.md"]}
            ],
        )
        result = find_relevant_memories(
            "what is my role", tmp_path, provider,
            already_surfaced=set(),
            recent_tools=[], session_bytes_used=0,
            auto_memory_enabled=True,
        )
        assert len(result.headers) == 1
        assert result.headers[0].id == "user/role"

    def test_already_surfaced_filtered_out(self, tmp_path: Path) -> None:
        _write_memory(tmp_path, "user/role", name="User role", desc="coding role")
        _write_memory(tmp_path, "user/prefs", name="User prefs", desc="preferences")
        provider = MockProvider(
            [],
            selector_responses=[
                {"filenames": ["user/role.md", "user/prefs.md"]}
            ],
        )
        result = find_relevant_memories(
            "what are my preferences", tmp_path, provider,
            already_surfaced={"user/role"},  # already surfaced this session
            recent_tools=[], session_bytes_used=0,
            auto_memory_enabled=True,
        )
        # user/role is filtered; only user/prefs remains
        assert len(result.headers) == 1
        assert result.headers[0].id == "user/prefs"

    def test_selector_error_falls_back_to_jaccard(self, tmp_path: Path) -> None:
        _write_memory(
            tmp_path, "user/role",
            name="User role", desc="coding preferences style",
        )
        # selector_responses=[] -> SelectorError on first call
        provider = MockProvider([], selector_responses=[])
        result = find_relevant_memories(
            "coding preferences style guide", tmp_path, provider,
            already_surfaced=set(),
            recent_tools=[], session_bytes_used=0,
            auto_memory_enabled=True,
        )
        # Jaccard fallback should surface the matching memory
        assert len(result.headers) >= 1
        assert result.headers[0].id == "user/role"

    def test_selector_error_falls_back_gracefully_no_match(
        self, tmp_path: Path
    ) -> None:
        _write_memory(tmp_path, "user/role", name="Z", desc="Z")
        provider = MockProvider([], selector_responses=[])
        result = find_relevant_memories(
            "completely unrelated query with many words here", tmp_path, provider,
            already_surfaced=set(),
            recent_tools=[], session_bytes_used=0,
            auto_memory_enabled=True,
        )
        # Jaccard fallback returns entries when all-zero (fallback to list[:n])
        assert isinstance(result.headers, list)
