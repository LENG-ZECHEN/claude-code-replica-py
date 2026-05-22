"""Phase B3 tests: SessionMemory.dump_json / load_json roundtrip.

`SessionMemory` is otherwise an in-process dict and dies with the
process. M3 adds an explicit, opt-in JSON serialization layer so the REPL
can auto-save on exit and auto-load on start without inventing a new
storage format. Atomic write via tempfile + os.replace mirrors what
ProjectMemory already does for its manifest, so a crash mid-dump leaves
the previous snapshot intact.

Test plan: RUNTIME_ACTIVATION_PLAN.md section 3.2 (session-persist).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from simple_coding_agent.memory import MemoryEntry, MemoryType, SessionMemory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    body: str,
    name: str,
    memory_type: MemoryType,
    entry_id: str,
) -> MemoryEntry:
    return MemoryEntry(
        name=name,
        body=body,
        type=memory_type,
        id=entry_id,
        created_at="2026-05-21T00:00:00+00:00",
        tags=["alpha", "beta"],
    )


# ---------------------------------------------------------------------------
# 1. Roundtrip preserves entries
# ---------------------------------------------------------------------------


def test_dump_load_roundtrip_preserves_entries(tmp_path: Path) -> None:
    mem = SessionMemory()
    e1 = _make_entry(
        body="alpha body",
        name="alpha",
        memory_type=MemoryType.USER,
        entry_id="id-1",
    )
    e2 = _make_entry(
        body="beta body",
        name="beta",
        memory_type=MemoryType.FEEDBACK,
        entry_id="id-2",
    )
    mem.add(e1)
    mem.add(e2)

    path = tmp_path / "session.json"
    mem.dump_json(path)

    loaded = SessionMemory.load_json(path)

    loaded_entries = {e.id: e for e in loaded.all()}
    assert loaded_entries["id-1"].body == "alpha body"
    assert loaded_entries["id-1"].name == "alpha"
    assert loaded_entries["id-1"].type == MemoryType.USER
    assert loaded_entries["id-1"].tags == ["alpha", "beta"]
    assert loaded_entries["id-2"].type == MemoryType.FEEDBACK


# ---------------------------------------------------------------------------
# 2. Missing file -> empty store, no exception
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_empty_store(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    assert not path.exists()

    loaded = SessionMemory.load_json(path)

    assert isinstance(loaded, SessionMemory)
    assert loaded.all() == []


# ---------------------------------------------------------------------------
# 3. Corrupted JSON -> empty store + warning, never raises
# ---------------------------------------------------------------------------


def test_load_corrupted_json_returns_empty_with_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "corrupt.json"
    path.write_text("{this is not valid json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="simple_coding_agent.memory"):
        loaded = SessionMemory.load_json(path)

    assert isinstance(loaded, SessionMemory)
    assert loaded.all() == []
    assert any(
        "session_memory" in rec.message.lower()
        or "json" in rec.message.lower()
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# 4. Atomic write — previous file is preserved on dump failure
# ---------------------------------------------------------------------------


def test_dump_atomic_write_via_tempfile_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-existing file content survives a mid-dump failure."""
    path = tmp_path / "session.json"
    initial = {"entries": [{
        "id": "id-prev",
        "name": "prev",
        "body": "prev body",
        "type": "user",
        "tags": [],
        "created_at": "2026-05-20T00:00:00+00:00",
    }]}
    path.write_text(json.dumps(initial), encoding="utf-8")

    mem = SessionMemory()
    mem.add(_make_entry(
        body="new body",
        name="new",
        memory_type=MemoryType.PROJECT,
        entry_id="id-new",
    ))

    def _boom(*_a: Any, **_kw: Any) -> None:
        raise OSError("simulated failure")

    monkeypatch.setattr("os.replace", _boom)

    with pytest.raises(OSError):
        mem.dump_json(path)

    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded == initial


# ---------------------------------------------------------------------------
# 5. All four MemoryType values round-trip
# ---------------------------------------------------------------------------


def test_dump_preserves_memory_type(tmp_path: Path) -> None:
    mem = SessionMemory()
    type_values = list(MemoryType)
    for idx, mtype in enumerate(type_values):
        mem.add(_make_entry(
            body=f"body for {mtype.value}",
            name=f"name-{mtype.value}",
            memory_type=mtype,
            entry_id=f"id-{idx}",
        ))

    path = tmp_path / "types.json"
    mem.dump_json(path)
    loaded = SessionMemory.load_json(path)

    loaded_types = {e.type for e in loaded.all()}
    assert loaded_types == set(type_values)


# ---------------------------------------------------------------------------
# 6. Forward compatibility — extra fields ignored
# ---------------------------------------------------------------------------


def test_load_ignores_extra_fields_for_forward_compat(tmp_path: Path) -> None:
    """A future format with extra fields must still load on old code."""
    payload = {
        "version": 99,
        "future_root_field": {"nested": True},
        "entries": [
            {
                "id": "id-a",
                "name": "alpha",
                "body": "alpha body",
                "type": "user",
                "tags": ["t"],
                "created_at": "2026-05-21T00:00:00+00:00",
                "future_field": "ignored",
                "another_future": 12,
            },
        ],
    }
    path = tmp_path / "future.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = SessionMemory.load_json(path)

    entries = loaded.all()
    assert len(entries) == 1
    assert entries[0].id == "id-a"
    assert entries[0].body == "alpha body"
    assert entries[0].type == MemoryType.USER


# ---------------------------------------------------------------------------
# 7. Empty store round-trips without error
# ---------------------------------------------------------------------------


def test_dump_load_empty_store_roundtrip(tmp_path: Path) -> None:
    """Dump/load on an empty SessionMemory yields another empty store."""
    mem = SessionMemory()
    path = tmp_path / "empty.json"

    mem.dump_json(path)
    loaded = SessionMemory.load_json(path)

    assert loaded.all() == []
    # The on-disk payload still has the entries key so consumers can iterate
    # without conditional checks.
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["entries"] == []


# ---------------------------------------------------------------------------
# 8. dump_json creates missing parent directories
# ---------------------------------------------------------------------------


def test_dump_creates_missing_parent_directories(tmp_path: Path) -> None:
    """Writing to a nested path auto-creates the parent (.simple-agent dir)."""
    nested = tmp_path / "nested" / "deep" / "session.json"
    assert not nested.parent.exists()

    mem = SessionMemory()
    mem.add(_make_entry(
        body="nested body",
        name="nested",
        memory_type=MemoryType.REFERENCE,
        entry_id="id-nested",
    ))
    mem.dump_json(nested)

    assert nested.exists()
    loaded = SessionMemory.load_json(nested)
    assert {e.id for e in loaded.all()} == {"id-nested"}


# ---------------------------------------------------------------------------
# 9. created_at timestamp round-trips losslessly
# ---------------------------------------------------------------------------


def test_dump_preserves_created_at_timestamp(tmp_path: Path) -> None:
    """`created_at` survives JSON round-trip byte-for-byte."""
    ts = "2026-05-21T12:34:56.789012+00:00"
    mem = SessionMemory()
    mem.add(MemoryEntry(
        name="ts-entry",
        body="body",
        type=MemoryType.PROJECT,
        id="ts-id",
        created_at=ts,
        tags=[],
    ))

    path = tmp_path / "ts.json"
    mem.dump_json(path)
    loaded = SessionMemory.load_json(path)

    entries = loaded.all()
    assert len(entries) == 1
    assert entries[0].created_at == ts


# ---------------------------------------------------------------------------
# Patch 2 (Mem8): load-time secret filter on SessionMemory.load_json
# ---------------------------------------------------------------------------


def test_session_memory_load_json_skips_entries_with_bearer_token(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A snapshot with a secret-tainted entry loads the safe one only.

    Mirrors ``ProjectMemory.save``'s secret rejection so a malicious or
    accidentally-tainted ``session_memory.json`` can never re-hydrate
    secrets into the active session.
    """
    payload: dict[str, Any] = {
        "version": 1,
        "entries": [
            {
                "id": "safe-entry-1",
                "name": "safe",
                "body": "User prefers Python.",
                "type": "user",
                "tags": [],
                "created_at": "2026-05-21T00:00:00+00:00",
            },
            {
                "id": "tainted-entry-1",
                "name": "tainted",
                "body": "Authorization: Bearer eyJ.abc.def_123ghi",
                "type": "reference",
                "tags": [],
                "created_at": "2026-05-21T00:00:00+00:00",
            },
        ],
    }
    path = tmp_path / "session_memory.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="simple_coding_agent.memory"):
        loaded = SessionMemory.load_json(path)

    entries = loaded.all()
    assert len(entries) == 1
    assert entries[0].id == "safe-entry-1"
    assert any(
        "tainted-entry-1" in rec.message and "secret" in rec.message.lower()
        for rec in caplog.records
    )
