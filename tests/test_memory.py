"""Phase 6 / Step 2: MemoryStore tests — written before implementation (TDD)."""

from __future__ import annotations

import json
import os

import pytest

from simple_coding_agent.memory import (
    MemoryEntry,
    MemorySelector,
    MemoryType,
    ProjectMemory,
    SessionMemory,
)

# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------

def test_memory_entry_fields() -> None:
    entry = MemoryEntry(
        name="user-role",
        body="User is a senior Python engineer.",
        type=MemoryType.USER,
    )
    assert entry.name == "user-role"
    assert entry.body == "User is a senior Python engineer."
    assert entry.type == MemoryType.USER
    assert entry.id != ""
    assert entry.created_at != ""
    assert entry.tags == []


def test_memory_entry_with_tags() -> None:
    entry = MemoryEntry(
        name="testing-pref",
        body="Always write tests first.",
        type=MemoryType.FEEDBACK,
        tags=["testing", "tdd"],
    )
    assert "testing" in entry.tags
    assert "tdd" in entry.tags


def test_memory_type_values() -> None:
    assert MemoryType.USER == "user"
    assert MemoryType.FEEDBACK == "feedback"
    assert MemoryType.PROJECT == "project"
    assert MemoryType.REFERENCE == "reference"


# ---------------------------------------------------------------------------
# SessionMemory
# ---------------------------------------------------------------------------

def test_session_memory_add_and_get() -> None:
    mem = SessionMemory()
    entry = MemoryEntry(name="fact", body="session fact", type=MemoryType.PROJECT)
    mem.add(entry)
    assert mem.get(entry.id) is entry


def test_session_memory_get_unknown_returns_none() -> None:
    mem = SessionMemory()
    assert mem.get("nonexistent") is None


def test_session_memory_all_returns_all() -> None:
    mem = SessionMemory()
    mem.add(MemoryEntry(name="a", body="body a", type=MemoryType.USER))
    mem.add(MemoryEntry(name="b", body="body b", type=MemoryType.FEEDBACK))
    assert len(mem.all()) == 2


def test_session_memory_search_by_keyword() -> None:
    mem = SessionMemory()
    mem.add(MemoryEntry(name="x", body="Python is the best language.", type=MemoryType.USER))
    mem.add(MemoryEntry(name="y", body="Use pytest for testing.", type=MemoryType.FEEDBACK))
    results = mem.search("python")
    assert len(results) == 1
    assert "Python" in results[0].body


def test_session_memory_search_case_insensitive() -> None:
    mem = SessionMemory()
    mem.add(MemoryEntry(name="z", body="Always use TYPE HINTS.", type=MemoryType.FEEDBACK))
    assert len(mem.search("type hints")) == 1
    assert len(mem.search("TYPE HINTS")) == 1


def test_session_memory_search_no_match_returns_empty() -> None:
    mem = SessionMemory()
    mem.add(MemoryEntry(name="a", body="some content", type=MemoryType.USER))
    assert mem.search("nonexistent keyword") == []


def test_session_memory_search_matches_name_too() -> None:
    mem = SessionMemory()
    mem.add(MemoryEntry(name="auth-preference", body="Use JWT.", type=MemoryType.FEEDBACK))
    results = mem.search("auth-preference")
    assert len(results) == 1


def test_session_memory_to_snippets() -> None:
    """to_snippets() returns list[str] ready for ContextBuilder.memory_snippets."""
    mem = SessionMemory()
    mem.add(MemoryEntry(name="f1", body="Prefer functional style.", type=MemoryType.FEEDBACK))
    mem.add(MemoryEntry(name="u1", body="User is backend-focused.", type=MemoryType.USER))
    snippets = mem.to_snippets()
    assert len(snippets) == 2
    assert all(isinstance(s, str) for s in snippets)
    assert any("Prefer functional style." in s for s in snippets)


def test_session_memory_to_snippets_empty() -> None:
    mem = SessionMemory()
    assert mem.to_snippets() == []


# ---------------------------------------------------------------------------
# MemorySelector
# ---------------------------------------------------------------------------

def test_memory_selector_scores_overlap_higher_than_unrelated() -> None:
    selector = MemorySelector()
    related = selector.score("python pytest backend", "Prefer pytest for Python tests.")
    unrelated = selector.score("python pytest backend", "Use blue for dashboard charts.")
    assert related > unrelated


def test_memory_selector_score_is_case_insensitive() -> None:
    selector = MemorySelector()
    lower = selector.score("python tests", "python tests")
    mixed = selector.score("PYTHON tests", "Python TESTS")
    assert mixed == lower


def test_memory_selector_empty_query_scores_zero() -> None:
    selector = MemorySelector()
    assert selector.score("", "some entry text") == 0.0
    assert selector.score("!!!", "some entry text") == 0.0


def test_memory_selector_empty_entry_scores_zero() -> None:
    selector = MemorySelector()
    assert selector.score("python", "") == 0.0
    assert selector.score("python", "!!!") == 0.0


def test_memory_selector_select_top_n_caps_results() -> None:
    entries = [
        MemoryEntry(name=f"python-{i}", body=f"python pytest topic {i}", type=MemoryType.PROJECT)
        for i in range(6)
    ]
    selected = MemorySelector().select_top_n("python pytest", entries, n=3)
    assert len(selected) == 3


def test_memory_selector_select_top_n_sorts_by_score_descending() -> None:
    entries = [
        MemoryEntry(name="one", body="python", type=MemoryType.PROJECT),
        MemoryEntry(name="three", body="python pytest backend", type=MemoryType.PROJECT),
        MemoryEntry(name="two", body="python pytest", type=MemoryType.PROJECT),
    ]
    selected = MemorySelector().select_top_n("python pytest backend", entries, n=3)
    assert [entry.name for entry in selected] == ["three", "two", "one"]


def test_memory_selector_select_top_n_preserves_original_order_for_ties() -> None:
    entries = [
        MemoryEntry(name="first", body="python", type=MemoryType.PROJECT),
        MemoryEntry(name="second", body="python", type=MemoryType.PROJECT),
        MemoryEntry(name="third", body="python", type=MemoryType.PROJECT),
    ]
    selected = MemorySelector().select_top_n("python", entries, n=3)
    assert [entry.name for entry in selected] == ["first", "second", "third"]


def test_memory_selector_select_top_n_all_zero_falls_back_to_first_n() -> None:
    entries = [
        MemoryEntry(name="first", body="alpha", type=MemoryType.PROJECT),
        MemoryEntry(name="second", body="beta", type=MemoryType.PROJECT),
        MemoryEntry(name="third", body="gamma", type=MemoryType.PROJECT),
    ]
    selected = MemorySelector().select_top_n("zzz", entries, n=2)
    assert [entry.name for entry in selected] == ["first", "second"]


def test_memory_selector_select_top_n_does_not_mutate_input() -> None:
    entries = [
        MemoryEntry(name="low", body="python", type=MemoryType.PROJECT),
        MemoryEntry(name="high", body="python pytest backend", type=MemoryType.PROJECT),
    ]
    original_ids = [entry.id for entry in entries]
    selected = MemorySelector().select_top_n("python pytest backend", entries, n=2)
    assert [entry.id for entry in entries] == original_ids
    assert [entry.name for entry in selected] == ["high", "low"]


# ---------------------------------------------------------------------------
# ProjectMemory (file-backed)
# ---------------------------------------------------------------------------

def test_project_memory_save_and_load(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    entry = MemoryEntry(name="pref-no-emoji", body="No emojis in output.", type=MemoryType.FEEDBACK)
    pm.save(entry)
    loaded = pm.load(entry.id)
    assert loaded is not None
    assert loaded.name == "pref-no-emoji"
    assert loaded.body == "No emojis in output."
    assert loaded.type == MemoryType.FEEDBACK


def test_project_memory_save_writes_json_file(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    entry = MemoryEntry(name="x", body="some body", type=MemoryType.USER)
    pm.save(entry)
    json_path = os.path.join(str(tmp_path), f"{entry.id}.json")
    assert os.path.exists(json_path)
    with open(json_path) as f:
        data = json.load(f)
    assert data["name"] == "x"
    assert data["body"] == "some body"
    assert data["type"] == "user"


def test_project_memory_load_unknown_returns_none(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    assert pm.load("nonexistent-id") is None


def test_project_memory_load_rejects_path_traversal(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    with pytest.raises(ValueError, match="invalid memory entry id"):
        pm.load("../outside")


def test_project_memory_delete_rejects_path_traversal(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    outside = tmp_path / ".." / "outside.json"
    with pytest.raises(ValueError, match="invalid memory entry id"):
        pm.delete("../outside")
    assert not outside.exists()


def test_project_memory_save_rejects_path_traversal(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    entry = MemoryEntry(
        id="../outside",
        name="bad",
        body="body",
        type=MemoryType.PROJECT,
    )
    with pytest.raises(ValueError, match="invalid memory entry id"):
        pm.save(entry)


def test_project_memory_all_entries(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="a", body="a body", type=MemoryType.USER))
    pm.save(MemoryEntry(name="b", body="b body", type=MemoryType.PROJECT))
    entries = pm.all()
    assert len(entries) == 2


def test_project_memory_search_by_keyword(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="style", body="Prefer immutable data.", type=MemoryType.FEEDBACK))
    pm.save(MemoryEntry(name="model", body="Use Sonnet for main tasks.", type=MemoryType.REFERENCE))
    results = pm.search("immutable")
    assert len(results) == 1
    assert "immutable" in results[0].body


def test_project_memory_does_not_store_env_values(tmp_path: object) -> None:
    """Memory body must not contain secret-looking values."""
    pm = ProjectMemory(storage_dir=str(tmp_path))
    with pytest.raises(ValueError, match="secret"):
        pm.save(MemoryEntry(
            name="bad",
            body="API_KEY=sk-abc123secret",
            type=MemoryType.REFERENCE,
        ))


def test_project_memory_save_rejects_bearer_token(tmp_path: object) -> None:
    """Patch 2 (Mem1): Bearer token bodies are rejected by save()."""
    pm = ProjectMemory(storage_dir=str(tmp_path))
    with pytest.raises(ValueError, match="secret"):
        pm.save(MemoryEntry(
            name="bad-bearer",
            body="Authorization: Bearer eyJ.abc.def_123ghi",
            type=MemoryType.REFERENCE,
        ))


def test_project_memory_save_rejects_aws_access_key(tmp_path: object) -> None:
    """Patch 2 (Mem1): AWS access key IDs (AKIA + 16 chars) are rejected."""
    pm = ProjectMemory(storage_dir=str(tmp_path))
    with pytest.raises(ValueError, match="secret"):
        pm.save(MemoryEntry(
            name="bad-aws",
            body="my key is AKIAIOSFODNN7EXAMPLE for staging",
            type=MemoryType.REFERENCE,
        ))


def test_project_memory_save_rejects_pem_block(tmp_path: object) -> None:
    """Patch 2 (Mem1): PEM PRIVATE KEY block headers are rejected."""
    pm = ProjectMemory(storage_dir=str(tmp_path))
    with pytest.raises(ValueError, match="secret"):
        pm.save(MemoryEntry(
            name="bad-pem",
            body="-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
            type=MemoryType.REFERENCE,
        ))


def test_project_memory_manifest_written(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="fact-a", body="body a", type=MemoryType.USER))
    pm.save(MemoryEntry(name="fact-b", body="body b", type=MemoryType.PROJECT))
    manifest_path = os.path.join(str(tmp_path), "MEMORY.md")
    assert os.path.exists(manifest_path)
    content = open(manifest_path).read()
    assert "fact-a" in content
    assert "fact-b" in content


def test_manifest_escapes_brackets_in_entry_name(tmp_path: object) -> None:
    """Patch 6 (Mem3): square brackets in entry name are escaped."""
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="weird ] name", body="b", type=MemoryType.USER))
    content = open(os.path.join(str(tmp_path), "MEMORY.md")).read()
    # Escaped form must be present; raw bracket must not break the link.
    assert "weird \\] name" in content
    # The remainder of the link must remain intact.
    assert "](" in content


def test_manifest_escapes_parens_in_entry_name(tmp_path: object) -> None:
    """Patch 6 (Mem3): parentheses in entry name are escaped."""
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="hax (link) name", body="b", type=MemoryType.USER))
    content = open(os.path.join(str(tmp_path), "MEMORY.md")).read()
    assert "hax \\(link\\) name" in content


def test_manifest_collapses_newlines_in_entry_name(tmp_path: object) -> None:
    """Patch 6 (Mem3): newlines in entry name collapse to spaces.

    Without this guard a name like ``"foo\\nbar"`` would split the
    manifest line so a downstream parser sees two entries instead of one.
    """
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="line\none\nthree", body="b", type=MemoryType.USER))
    content = open(os.path.join(str(tmp_path), "MEMORY.md")).read()
    # The escaped name should be on a single line.
    matching = [
        line for line in content.splitlines() if "line" in line and "three" in line
    ]
    assert len(matching) == 1
    assert "\n" not in matching[0]


def test_project_memory_to_snippets(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(name="s1", body="User prefers Python.", type=MemoryType.USER))
    snippets = pm.to_snippets()
    assert len(snippets) == 1
    assert "User prefers Python." in snippets[0]


def test_project_memory_to_snippets_without_query_returns_all_entries(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    for i in range(7):
        pm.save(MemoryEntry(name=f"entry-{i}", body=f"body {i}", type=MemoryType.PROJECT))

    snippets = pm.to_snippets(query=None)

    assert len(snippets) == 7


def test_project_memory_to_snippets_with_query_returns_top_five_relevant(
    tmp_path: object,
) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    for i in range(6):
        pm.save(MemoryEntry(
            name=f"python-{i}",
            body=f"python pytest backend relevant memory {i}",
            type=MemoryType.PROJECT,
        ))
    pm.save(MemoryEntry(
        name="unrelated",
        body="gardening watercolor recipes",
        type=MemoryType.PROJECT,
    ))

    snippets = pm.to_snippets(query="Need pytest help for a Python backend")

    assert len(snippets) == 5
    assert all("python-" in snippet for snippet in snippets)
    assert not any("unrelated" in snippet for snippet in snippets)


def test_project_memory_to_snippets_with_query_keeps_existing_format(
    tmp_path: object,
) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    pm.save(MemoryEntry(
        name="testing-pref",
        body="Prefer pytest tests.",
        type=MemoryType.FEEDBACK,
    ))

    snippets = pm.to_snippets(query="pytest")

    assert snippets == ["[feedback] testing-pref: Prefer pytest tests."]


def test_project_memory_delete(tmp_path: object) -> None:
    pm = ProjectMemory(storage_dir=str(tmp_path))
    entry = MemoryEntry(name="temp", body="temporary note", type=MemoryType.PROJECT)
    pm.save(entry)
    pm.delete(entry.id)
    assert pm.load(entry.id) is None
    assert not any(e.id == entry.id for e in pm.all())
