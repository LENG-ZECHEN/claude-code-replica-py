"""M1-B1: memory CLI tests — written before implementation (TDD).

Covers Section 3.2 of RUNTIME_ACTIVATION_PLAN.md:
 - `simple-agent memory {add,list,delete,search,show}` round-trip.
 - Secret guard + path-traversal guard surface as non-zero exit.
 - Storage dir resolves from SIMPLE_AGENT_MEMORY_DIR or workspace default.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_coding_agent.cli import main


def _run(
    *argv: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> int:
    """Invoke `simple-agent memory ...` with optional env / cwd overrides."""
    if monkeypatch is not None:
        if env is not None:
            for k, v in env.items():
                monkeypatch.setenv(k, v)
        if cwd is not None:
            monkeypatch.chdir(str(cwd))
    return main(["memory", *argv])


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

def test_add_creates_entry_json_on_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    storage = tmp_path / "mem"
    rc = _run(
        "add", "user", "fav-editor", "I prefer Helix.",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    json_files = sorted(p for p in storage.iterdir() if p.suffix == ".json")
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["name"] == "fav-editor"
    assert data["body"] == "I prefer Helix."
    assert data["type"] == "user"


def test_add_rejects_secret_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = tmp_path / "mem"
    rc = _run(
        "add", "user", "leaked", "API_KEY=secretsecret",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 2
    if storage.exists():
        assert not any(p.suffix == ".json" for p in storage.iterdir())
    err = capsys.readouterr().err.lower()
    assert "secret" in err


def test_add_rejects_path_traversal_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = tmp_path / "mem"
    rc = _run(
        "add", "user", "../../etc/passwd", "body",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 2
    err = capsys.readouterr().err.lower()
    assert "invalid" in err or "memory entry id" in err


def test_add_rejects_unknown_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = tmp_path / "mem"
    rc = _run(
        "add", "foo", "name", "body",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 2
    err = capsys.readouterr().err.lower()
    # Hint should list valid types.
    assert "user" in err
    assert "feedback" in err


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_prints_all_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = tmp_path / "mem"
    for name in ("a", "b", "c"):
        _run(
            "add", "user", name, f"body of {name}",
            env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
            monkeypatch=monkeypatch,
        )
    capsys.readouterr()  # drop the add output
    rc = _run(
        "list",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "a" in out and "b" in out and "c" in out
    nonempty = [ln for ln in out.splitlines() if ln.strip()]
    assert len(nonempty) >= 3


def test_list_type_filter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = tmp_path / "mem"
    _run("add", "user", "u1", "user body",
         env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
         monkeypatch=monkeypatch)
    _run("add", "feedback", "f1", "feedback body",
         env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
         monkeypatch=monkeypatch)
    capsys.readouterr()
    rc = _run(
        "list", "--type", "feedback",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "f1" in out
    assert "u1" not in out


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_removes_file_and_updates_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    storage = tmp_path / "mem"
    _run("add", "user", "removeme", "bye",
         env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
         monkeypatch=monkeypatch)
    assert (storage / "removeme.json").exists()

    rc = _run(
        "delete", "removeme",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    assert not (storage / "removeme.json").exists()
    manifest = (storage / "MEMORY.md").read_text(encoding="utf-8")
    assert "removeme" not in manifest


def test_delete_missing_id_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    storage = tmp_path / "mem"
    storage.mkdir()
    rc = _run(
        "delete", "doesnotexist",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def test_search_substring_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = tmp_path / "mem"
    _run("add", "project", "stack", "we use fastapi in production",
         env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
         monkeypatch=monkeypatch)
    _run("add", "project", "tool", "we use jq for json",
         env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
         monkeypatch=monkeypatch)
    capsys.readouterr()
    rc = _run(
        "search", "fastapi",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "stack" in out
    assert "tool" not in out


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def test_show_prints_full_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    long_body = "first line\n" + ("paragraph " * 60) + "\nlast line"
    storage = tmp_path / "mem"
    _run("add", "user", "deep-thought", long_body,
         env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
         monkeypatch=monkeypatch)
    capsys.readouterr()
    rc = _run(
        "show", "deep-thought",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "first line" in out
    assert "last line" in out


# ---------------------------------------------------------------------------
# storage-dir resolution
# ---------------------------------------------------------------------------

def test_storage_dir_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    target = tmp_path / "envdir" / "mem"
    rc = _run(
        "add", "user", "named", "body",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(target)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    assert (target / "named.json").exists()


def test_storage_dir_default_under_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.delenv("SIMPLE_AGENT_MEMORY_DIR", raising=False)
    monkeypatch.chdir(str(tmp_path))
    rc = _run("add", "user", "named", "body", monkeypatch=monkeypatch)
    assert rc == 0
    default_dir = tmp_path / ".simple-agent" / "memory"
    assert (default_dir / "named.json").exists()


# ---------------------------------------------------------------------------
# Patch 6 (Mem5): memory update subcommand
# ---------------------------------------------------------------------------


def test_update_changes_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """``update`` rewrites the body while preserving identity."""
    storage = tmp_path / "mem"
    assert _run(
        "add", "user", "fav-editor", "I prefer Helix.",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    ) == 0

    rc = _run(
        "update", "fav-editor", "Actually", "I", "switched", "to", "Vim.",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    data = json.loads((storage / "fav-editor.json").read_text(encoding="utf-8"))
    assert data["body"] == "Actually I switched to Vim."


def test_update_preserves_id_and_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """``update`` must not change id, type, name, or created_at."""
    storage = tmp_path / "mem"
    assert _run(
        "add", "feedback", "tabs", "user prefers tabs",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    ) == 0
    before = json.loads((storage / "tabs.json").read_text(encoding="utf-8"))

    assert _run(
        "update", "tabs", "user prefers spaces now",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    ) == 0

    after = json.loads((storage / "tabs.json").read_text(encoding="utf-8"))
    assert after["id"] == before["id"]
    assert after["type"] == before["type"] == "feedback"
    assert after["name"] == before["name"]
    assert after["created_at"] == before["created_at"]
    assert after["body"] == "user prefers spaces now"


def test_update_unknown_id_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Updating a missing id surfaces as exit code 2 with a clear error."""
    storage = tmp_path / "mem"
    rc = _run(
        "update", "doesnotexist", "some", "new", "body",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 2
    err = capsys.readouterr().err.lower()
    assert "no memory entry" in err


def test_update_rejects_secret_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``update`` honours the same secret-rejection guard as ``add``."""
    storage = tmp_path / "mem"
    assert _run(
        "add", "user", "harmless", "nothing to see here",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    ) == 0

    rc = _run(
        "update", "harmless", "API_KEY=abc123xyz",
        env={"SIMPLE_AGENT_MEMORY_DIR": str(storage)},
        monkeypatch=monkeypatch,
    )
    assert rc == 2
    err = capsys.readouterr().err.lower()
    assert "secret" in err
    # Disk content must remain unchanged.
    data = json.loads((storage / "harmless.json").read_text(encoding="utf-8"))
    assert data["body"] == "nothing to see here"
