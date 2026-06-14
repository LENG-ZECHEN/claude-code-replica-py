"""Tests for DreamConsolidator (dream.py) — M6 exit gate.

Exit gate assertions (map directly to test cases):
  (a) Gate returns False → DreamResult(0,0,0,()) without holding lock
  (b) Deterministic dedup merges near-identical entries (Jaccard ≥ threshold)
  (c) Deterministic dedup KEEPS NEWEST entry (by mtime) in a near-identical pair
  (d) Deterministic dedup does NOT merge dissimilar entries (Jaccard < threshold)
  (e) Deterministic prune removes oldest entries when count > MANIFEST_MAX_ENTRIES
  (f) Idempotency: second run over already-consolidated store → merged=0, pruned=0
  (g) LLM mode: all 4 Phase headings in the task_prompt sent to ForkedAgentRunner
  (h) LLM mode: can_use_tool gate ALLOWS list_files (read-only tool) → is_error=False
  (i) LLM mode: can_use_tool gate BLOCKS run_shell (not in whitelist) → is_error=True
  (j) LLM mode: rollback_consolidation_lock called when ForkedAgentRunner.run raises
  (k) DreamResult is a frozen dataclass (assignment raises FrozenInstanceError)
  (l) Path-traversal guard: ProjectMemory.save rejects '../evil' entry id
  (m) Secret guard: ProjectMemory.save rejects bodies matching secret patterns
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from simple_coding_agent.consolidation_lock import DreamGateDecision
from simple_coding_agent.dream import (
    MANIFEST_MAX_ENTRIES,
    DreamConsolidator,
    DreamResult,
)
from simple_coding_agent.forked_agent import ForkedAgentRunner
from simple_coding_agent.memory import MemoryEntry, MemoryType, ProjectMemory
from simple_coding_agent.provider import MockProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gate_pass(sessions: tuple[str, ...] = ()) -> DreamGateDecision:
    """Gate decision: should_dream=True, lock held, no prior lock file."""
    return DreamGateDecision(should_dream=True, prior_mtime=0.0, sessions_since=sessions)


_GATE_FAIL = DreamGateDecision(should_dream=False, prior_mtime=None, sessions_since=())


def _save(memory_dir: Path, entry_id: str, body: str, mtime_offset: float = 0.0) -> None:
    """Write a MemoryEntry to memory_dir and optionally shift its mtime."""
    pm = ProjectMemory(str(memory_dir))
    pm.save(MemoryEntry(
        id=entry_id,
        name=entry_id.replace("-", " ").title(),
        body=body,
        type=MemoryType.PROJECT,
    ))
    if mtime_offset:
        md = memory_dir / f"{entry_id}.md"
        t = time.time() + mtime_offset
        os.utime(md, (t, t))


# ---------------------------------------------------------------------------
# (k) DreamResult is frozen
# ---------------------------------------------------------------------------


def test_dream_result_is_frozen() -> None:
    """(k) DreamResult is frozen: assigning a field raises an exception."""
    r = DreamResult(merged=1, pruned=0, runs=0, written_paths=())
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError or AttributeError
        r.merged = 0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# (a) Gate returns False → no-op DreamResult, no lock acquired
# ---------------------------------------------------------------------------


def test_gate_false_returns_noop(tmp_path: Path) -> None:
    """(a) When the gate says no, DreamResult(0,0,0,()) is returned."""
    memory_dir = tmp_path / "mem"
    memory_dir.mkdir(parents=True, exist_ok=True)
    lock = tmp_path / ".consolidate-lock"

    consolidator = DreamConsolidator(memory_dir=memory_dir)

    with patch("simple_coding_agent.dream.should_dream", return_value=_GATE_FAIL):
        result = consolidator.consolidate(lock, now_ms=1_000_000.0)

    assert result == DreamResult(merged=0, pruned=0, runs=0, written_paths=())
    assert not lock.exists()  # lock never acquired


# ---------------------------------------------------------------------------
# (b) Deterministic dedup merges near-identical entries
# ---------------------------------------------------------------------------


def test_deterministic_dedup_merges_near_identical(tmp_path: Path) -> None:
    """(b) Two entries with identical body collapse into one; merged=1."""
    memory_dir = tmp_path / "mem"
    body = "user prefers terse responses without trailing summaries after each turn"
    _save(memory_dir, "entry-a", body, mtime_offset=-3600)  # older
    _save(memory_dir, "entry-b", body, mtime_offset=0.0)    # newer

    lock = tmp_path / ".consolidate-lock"
    consolidator = DreamConsolidator(memory_dir=memory_dir)  # provider=None

    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass()):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            result = consolidator.consolidate(lock, now_ms=1_000_000.0)

    assert result.merged == 1
    pm = ProjectMemory(str(memory_dir))
    assert len(pm.all()) == 1


# ---------------------------------------------------------------------------
# (c) Deterministic dedup keeps the NEWEST entry
# ---------------------------------------------------------------------------


def test_deterministic_dedup_keeps_newest_by_mtime(tmp_path: Path) -> None:
    """(c) The entry with the later mtime survives; the older one is deleted."""
    memory_dir = tmp_path / "mem"
    body = "the user wants concise answers without verbose explanations"
    _save(memory_dir, "old-one", body, mtime_offset=-7200)  # 2 h ago
    _save(memory_dir, "new-one", body, mtime_offset=0.0)    # now

    lock = tmp_path / ".consolidate-lock"
    consolidator = DreamConsolidator(memory_dir=memory_dir)

    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass()):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            result = consolidator.consolidate(lock, now_ms=1_000_000.0)

    assert result.merged == 1
    pm = ProjectMemory(str(memory_dir))
    survivors = [e.id for e in pm.all()]
    assert "new-one" in survivors
    assert "old-one" not in survivors


# ---------------------------------------------------------------------------
# (d) Deterministic dedup does NOT merge dissimilar entries
# ---------------------------------------------------------------------------


def test_deterministic_no_merge_for_dissimilar_entries(tmp_path: Path) -> None:
    """(d) Entries with Jaccard < HIGH_JACCARD_THRESHOLD survive unmerged."""
    memory_dir = tmp_path / "mem"
    _save(memory_dir, "about-user", "The user is a data scientist working on Python pipelines")
    _save(
        memory_dir,
        "db-migrations",
        "Database schema migrations require careful transaction planning",
    )

    lock = tmp_path / ".consolidate-lock"
    consolidator = DreamConsolidator(memory_dir=memory_dir)

    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass()):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            result = consolidator.consolidate(lock, now_ms=1_000_000.0)

    assert result.merged == 0
    pm = ProjectMemory(str(memory_dir))
    assert len(pm.all()) == 2  # both entries survive


# ---------------------------------------------------------------------------
# (e) Deterministic prune removes oldest entries when count > MANIFEST_MAX_ENTRIES
# ---------------------------------------------------------------------------


def test_deterministic_prune_removes_excess_entries(tmp_path: Path) -> None:
    """(e) When count > MANIFEST_MAX_ENTRIES (200), oldest entries are pruned."""
    memory_dir = tmp_path / "mem"
    total = MANIFEST_MAX_ENTRIES + 3  # 203 entries
    for i in range(total):
        # Each entry has unique body to avoid dedup triggering
        body = f"unique entry about topic_{i} with keyword_{i}_specific"
        # Older entries have smaller i → lower mtime offset (further in the past)
        _save(memory_dir, f"e-{i:04d}", body, mtime_offset=float(i - total))

    lock = tmp_path / ".consolidate-lock"
    consolidator = DreamConsolidator(memory_dir=memory_dir)

    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass()):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            result = consolidator.consolidate(lock, now_ms=1_000_000.0)

    assert result.pruned == 3
    pm = ProjectMemory(str(memory_dir))
    assert len(pm.all()) == MANIFEST_MAX_ENTRIES


# ---------------------------------------------------------------------------
# (f) Idempotency: second run → merged=0, pruned=0
# ---------------------------------------------------------------------------


def test_idempotency_second_run_is_noop(tmp_path: Path) -> None:
    """(f) After first consolidation removes a duplicate, second run finds none."""
    memory_dir = tmp_path / "mem"
    body = "user wants terse answers short concise quick fast brief minimal"
    _save(memory_dir, "dup-old", body, mtime_offset=-3600)
    _save(memory_dir, "dup-new", body, mtime_offset=0.0)

    lock = tmp_path / ".consolidate-lock"
    consolidator = DreamConsolidator(memory_dir=memory_dir)

    # First run: merges duplicates
    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass()):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            first = consolidator.consolidate(lock, now_ms=1_000_000.0)
    assert first.merged == 1

    # Second run: store is already clean → no-op
    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass()):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            second = consolidator.consolidate(lock, now_ms=2_000_000.0)
    assert second.merged == 0
    assert second.pruned == 0


# ---------------------------------------------------------------------------
# (g) LLM mode: 4-stage prompt delivered to ForkedAgentRunner
# ---------------------------------------------------------------------------


def test_llm_mode_prompt_contains_all_phases(tmp_path: Path) -> None:
    """(g) Provider receives a prompt with Phase 1–4 headings and session IDs."""
    memory_dir = tmp_path / "mem"
    memory_dir.mkdir(parents=True, exist_ok=True)

    sessions = ("sess-alpha", "sess-beta")
    provider = MockProvider([MockProvider.direct_answer("consolidated")])
    consolidator = DreamConsolidator(memory_dir=memory_dir, provider=provider)

    lock = tmp_path / ".consolidate-lock"
    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass(sessions)):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            result = consolidator.consolidate(lock, now_ms=1_000_000.0)

    assert result.runs == 1
    # task_prompt is the first (and only) user message in the first call
    first_call_msgs = provider.history[0].messages
    task_prompt = first_call_msgs[0]["content"]
    assert "Phase 1" in task_prompt
    assert "Phase 2" in task_prompt
    assert "Phase 3" in task_prompt
    assert "Phase 4" in task_prompt
    # sessions fed into prompt so agent doesn't scan to find scope
    assert "sess-alpha" in task_prompt
    assert "sess-beta" in task_prompt


# ---------------------------------------------------------------------------
# (h) LLM mode: can_use_tool gate ALLOWS read-only tools (is_error=False)
# ---------------------------------------------------------------------------


def test_can_use_tool_allows_list_files(tmp_path: Path) -> None:
    """(h) Gate allows list_files → tool_result has is_error=False."""
    memory_dir = tmp_path / "mem"
    memory_dir.mkdir(parents=True, exist_ok=True)

    tc_id = "list-call-1"
    provider = MockProvider([
        MockProvider.tool_call("list_files", {}, id=tc_id),
        MockProvider.direct_answer("done"),
    ])
    consolidator = DreamConsolidator(memory_dir=memory_dir, provider=provider)

    lock = tmp_path / ".consolidate-lock"
    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass()):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            consolidator.consolidate(lock, now_ms=1_000_000.0)

    # Second call contains the tool_result in the last user message
    second_call_msgs = provider.history[1].messages
    last_user = second_call_msgs[-1]
    assert last_user["role"] == "user"
    tool_results_content = last_user["content"]
    assert isinstance(tool_results_content, list)
    tr = next((t for t in tool_results_content if t.get("tool_use_id") == tc_id), None)
    assert tr is not None
    assert tr["is_error"] is False


# ---------------------------------------------------------------------------
# (i) LLM mode: can_use_tool gate BLOCKS disallowed tools (is_error=True)
# ---------------------------------------------------------------------------


def test_can_use_tool_blocks_disallowed_tool(tmp_path: Path) -> None:
    """(i) Gate denies run_shell → tool_result has is_error=True with reason."""
    memory_dir = tmp_path / "mem"
    memory_dir.mkdir(parents=True, exist_ok=True)

    tc_id = "shell-call-1"
    provider = MockProvider([
        MockProvider.tool_call("run_shell", {"command": "ls"}, id=tc_id),
        MockProvider.direct_answer("done"),
    ])
    consolidator = DreamConsolidator(memory_dir=memory_dir, provider=provider)

    lock = tmp_path / ".consolidate-lock"
    with patch("simple_coding_agent.dream.should_dream", return_value=_gate_pass()):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock"):
            consolidator.consolidate(lock, now_ms=1_000_000.0)

    second_call_msgs = provider.history[1].messages
    last_user = second_call_msgs[-1]
    tool_results_content = last_user["content"]
    tr = next((t for t in tool_results_content if t.get("tool_use_id") == tc_id), None)
    assert tr is not None
    assert tr["is_error"] is True
    assert "not available" in tr["content"]  # gate's deny reason


# ---------------------------------------------------------------------------
# (j) Rollback called on ForkedAgentRunner exception
# ---------------------------------------------------------------------------


def test_rollback_called_on_llm_failure(tmp_path: Path) -> None:
    """(j) When ForkedAgentRunner.run raises, rollback_consolidation_lock is called."""
    memory_dir = tmp_path / "mem"
    memory_dir.mkdir(parents=True, exist_ok=True)

    provider = MockProvider([MockProvider.direct_answer("ok")])
    consolidator = DreamConsolidator(memory_dir=memory_dir, provider=provider)
    lock = tmp_path / ".consolidate-lock"
    gate_decision = _gate_pass()

    with patch("simple_coding_agent.dream.should_dream", return_value=gate_decision):
        with patch("simple_coding_agent.dream.rollback_consolidation_lock") as mock_rb:
            with patch.object(
                ForkedAgentRunner,
                "run",
                side_effect=RuntimeError("provider exploded"),
            ):
                with pytest.raises(RuntimeError, match="provider exploded"):
                    consolidator.consolidate(lock, now_ms=1_000_000.0)

    mock_rb.assert_called_once_with(lock, gate_decision.prior_mtime)


# ---------------------------------------------------------------------------
# (l) Path-traversal guard via ProjectMemory.save()
# ---------------------------------------------------------------------------


def test_path_traversal_rejected_by_project_memory(tmp_path: Path) -> None:
    """(l) write_memory_entry with '../evil' id raises ValueError (path-traversal guard)."""
    pm = ProjectMemory(str(tmp_path / "mem"))
    with pytest.raises(ValueError, match="invalid memory entry id"):
        pm.save(MemoryEntry(
            id="../evil",
            name="evil",
            body="escape attempt",
            type=MemoryType.PROJECT,
        ))


# ---------------------------------------------------------------------------
# (m) Secret guard via ProjectMemory.save()
# ---------------------------------------------------------------------------


def test_secret_body_rejected_by_project_memory(tmp_path: Path) -> None:
    """(m) write_memory_entry with secret body raises ValueError (secret-detection guard)."""
    pm = ProjectMemory(str(tmp_path / "mem"))
    with pytest.raises(ValueError, match="secret"):
        pm.save(MemoryEntry(
            id="legit-id",
            name="legit",
            body="API_KEY=supersecret_value_12345",
            type=MemoryType.PROJECT,
        ))
