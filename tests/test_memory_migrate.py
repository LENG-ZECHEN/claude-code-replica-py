"""M1 / A1: migrate-format CLI tests (TDD — write before implementation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_coding_agent.memory_cli import main as cli_main


def _json_entry(entry_id: str, name: str, body: str, mem_type: str, tmp_path: Path) -> Path:
    data = {
        "id": entry_id,
        "name": name,
        "body": body,
        "type": mem_type,
        "tags": [],
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    path = tmp_path / f"{entry_id}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def test_migrate_converts_json_to_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(tmp_path))
    _json_entry("my-fact", "My Fact", "body text", "user", tmp_path)
    exit_code = cli_main(["migrate-format"])
    assert exit_code == 0
    md_path = tmp_path / "my-fact.md"
    assert md_path.exists(), "Expected .md file to be created"
    content = md_path.read_text(encoding="utf-8")
    assert "name: My Fact" in content
    assert "type: user" in content
    assert "body text" in content
    # Frontmatter must have --- delimiters
    assert content.startswith("---")


def test_migrate_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(tmp_path))
    _json_entry("existing-fact", "Existing", "original body", "project", tmp_path)
    # Run migrate once to create .md
    cli_main(["migrate-format"])
    md_path = tmp_path / "existing-fact.md"
    assert md_path.exists()
    # Record the content before second run
    content_before = md_path.read_text(encoding="utf-8")
    # Run migrate again — must not overwrite existing .md
    exit_code = cli_main(["migrate-format"])
    assert exit_code == 0
    content_after = md_path.read_text(encoding="utf-8")
    assert content_before == content_after, "migrate-format must not overwrite existing .md"
