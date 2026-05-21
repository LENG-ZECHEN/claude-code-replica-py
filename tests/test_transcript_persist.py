"""M4-D1: Transcript.dump_json / load_json roundtrip — TDD (RED first).

These tests pin the JSON serialization contract used by the M4 cross-process
session resume flow. The Transcript already exposes ``export()`` for logging,
but that surface preserves virtual messages and has no inverse — REPL
``/save`` and ``simple-agent --resume`` need a strict, schema-validated
round-trip that drops display-only state by default.

Test plan: RUNTIME_ACTIVATION_PLAN.md section 3.4 (`test_transcript_persist`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_coding_agent.models import (
    Message,
    MessageType,
    Role,
    ToolCall,
    ToolResult,
)
from simple_coding_agent.transcript import Transcript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixed_message(
    *,
    uuid: str,
    role: Role,
    content: str | list[ToolCall | ToolResult],
    timestamp: str = "2026-05-21T00:00:00+00:00",
    msg_type: MessageType = MessageType.TEXT,
    is_meta: bool = False,
    is_virtual: bool = False,
    is_compact_summary: bool = False,
) -> Message:
    return Message(
        uuid=uuid,
        role=role,
        content=content,
        timestamp=timestamp,
        type=msg_type,
        is_meta=is_meta,
        is_virtual=is_virtual,
        is_compact_summary=is_compact_summary,
    )


# ---------------------------------------------------------------------------
# 1. String-content messages round-trip
# ---------------------------------------------------------------------------


def test_dump_load_roundtrip_string_content_messages(tmp_path: Path) -> None:
    t = Transcript()
    t.append(_fixed_message(uuid="u1", role=Role.USER, content="hello"))
    t.append(_fixed_message(uuid="a1", role=Role.ASSISTANT, content="hi back"))

    path = tmp_path / "transcript.json"
    t.dump_json(path)

    loaded = Transcript.load_json(path)
    messages = loaded.all_messages()

    assert [m.uuid for m in messages] == ["u1", "a1"]
    assert [m.role for m in messages] == [Role.USER, Role.ASSISTANT]
    assert [m.content for m in messages] == ["hello", "hi back"]
    assert [m.timestamp for m in messages] == [
        "2026-05-21T00:00:00+00:00",
        "2026-05-21T00:00:00+00:00",
    ]


# ---------------------------------------------------------------------------
# 2. tool_use blocks round-trip with id/name/input
# ---------------------------------------------------------------------------


def test_dump_load_roundtrip_tool_call_messages(tmp_path: Path) -> None:
    tc = ToolCall(id="tc_1", name="read_file", input={"path": "src/app.py"})
    msg = _fixed_message(
        uuid="ast-1",
        role=Role.ASSISTANT,
        content=[tc],
        msg_type=MessageType.TOOL_USE,
    )
    t = Transcript()
    t.append(msg)

    path = tmp_path / "transcript.json"
    t.dump_json(path)
    loaded = Transcript.load_json(path)

    [restored] = loaded.all_messages()
    assert restored.type == MessageType.TOOL_USE
    assert isinstance(restored.content, list)
    [block] = restored.content
    assert isinstance(block, ToolCall)
    assert block.id == "tc_1"
    assert block.name == "read_file"
    assert block.input == {"path": "src/app.py"}


# ---------------------------------------------------------------------------
# 3. tool_result blocks round-trip with persisted_path
# ---------------------------------------------------------------------------


def test_dump_load_roundtrip_tool_result_messages(tmp_path: Path) -> None:
    tr = ToolResult(
        tool_use_id="tc_1",
        content="<persisted-output path=/tmp/x.txt size=80000 preview=...>",
        is_error=False,
        persisted_path="/tmp/x.txt",
        original_size=80_000,
    )
    msg = _fixed_message(
        uuid="usr-1",
        role=Role.USER,
        content=[tr],
        msg_type=MessageType.TOOL_RESULT,
        is_meta=True,
    )
    t = Transcript()
    t.append(msg)

    path = tmp_path / "transcript.json"
    t.dump_json(path)
    loaded = Transcript.load_json(path)

    [restored] = loaded.all_messages()
    assert restored.type == MessageType.TOOL_RESULT
    assert restored.is_meta is True
    assert isinstance(restored.content, list)
    [block] = restored.content
    assert isinstance(block, ToolResult)
    assert block.tool_use_id == "tc_1"
    assert block.persisted_path == "/tmp/x.txt"
    assert block.original_size == 80_000
    assert block.is_error is False


# ---------------------------------------------------------------------------
# 4. Compact boundary marker round-trips with its type and uuid
# ---------------------------------------------------------------------------


def test_dump_load_roundtrip_compact_boundary(tmp_path: Path) -> None:
    boundary = Message.compact_boundary()
    boundary.uuid = "boundary-uuid-1"
    boundary.timestamp = "2026-05-21T01:00:00+00:00"
    t = Transcript()
    t.append(_fixed_message(uuid="u1", role=Role.USER, content="before"))
    t.append(boundary)
    t.append(_fixed_message(uuid="u2", role=Role.USER, content="after"))

    path = tmp_path / "transcript.json"
    t.dump_json(path)
    loaded = Transcript.load_json(path)

    boundaries = [
        m for m in loaded.all_messages()
        if m.type == MessageType.COMPACT_BOUNDARY
    ]
    assert len(boundaries) == 1
    assert boundaries[0].uuid == "boundary-uuid-1"
    assert boundaries[0].role == Role.SYSTEM
    assert boundaries[0].is_meta is True
    # The boundary still slices correctly post-load.
    sliced = loaded.messages_after_compact_boundary()
    assert sliced[0].type == MessageType.COMPACT_BOUNDARY
    assert sliced[-1].content == "after"


# ---------------------------------------------------------------------------
# 5. is_virtual=True messages are dropped by default
# ---------------------------------------------------------------------------


def test_dump_excludes_virtual_by_default(tmp_path: Path) -> None:
    t = Transcript()
    t.append(_fixed_message(uuid="real-1", role=Role.USER, content="real"))
    t.append(_fixed_message(
        uuid="virtual-1",
        role=Role.USER,
        content="banner-only",
        is_virtual=True,
    ))
    t.append(_fixed_message(uuid="real-2", role=Role.ASSISTANT, content="reply"))

    path = tmp_path / "transcript.json"
    t.dump_json(path)
    loaded = Transcript.load_json(path)

    uuids = [m.uuid for m in loaded.all_messages()]
    assert uuids == ["real-1", "real-2"]

    # The on-disk JSON itself must omit the virtual row so an external
    # consumer never sees the dropped state.
    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized_uuids = [m["uuid"] for m in payload["messages"]]
    assert "virtual-1" not in serialized_uuids


# ---------------------------------------------------------------------------
# 6. Invalid schema raises ValueError with a clear message
# ---------------------------------------------------------------------------


def test_load_invalid_schema_raises_with_clear_message(tmp_path: Path) -> None:
    broken = {
        "version": 1,
        "messages": [
            {
                # 'uuid' missing — required by Message.
                "role": "user",
                "content": "hi",
                "timestamp": "2026-05-21T00:00:00+00:00",
                "type": "text",
            },
        ],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(ValueError, match="uuid"):
        Transcript.load_json(path)
