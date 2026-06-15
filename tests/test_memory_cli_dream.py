"""Tests for the `simple-agent memory dream` subcommand (M7).

Phase IDs: D3, D4.

Covers:
  (a) dry-run reports planned counts and writes NOTHING
  (b) --apply actually invokes DreamConsolidator and persists
  (c) --force bypasses a CLOSED M5 gate
  (d) a closed gate without --force is a no-op exit 0
  (e) bad dir → exit 2
  (f) --provider openai constructs an OpenAIProvider (mocked, no network)
  (g) MetricsCollector dream_runs / dream_merged / dream_pruned
  (h) --dream-on-exit OFF fires no dream at /exit, ON fires exactly one
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from simple_coding_agent.consolidation_lock import LOCK_FILE
from simple_coding_agent.dream import DreamConsolidator, DreamResult
from simple_coding_agent.memory import MemoryEntry, MemoryType, ProjectMemory
from simple_coding_agent.memory_cli import main
from simple_coding_agent.metrics import MetricsCollector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_entry(pm: ProjectMemory, id_: str, body: str) -> None:
    pm.save(MemoryEntry(
        id=id_,
        name=id_.replace("-", " ").title(),
        body=body,
        type=MemoryType.USER,
    ))


def _list_md_files(d: Path) -> set[str]:
    return {p.name for p in d.glob("*.md") if p.name != "MEMORY.md"}


# ---------------------------------------------------------------------------
# (a) dry-run reports planned counts and writes NOTHING
# ---------------------------------------------------------------------------

def test_dream_dryrun_no_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry-run reports planned counts; real memory dir is byte-identical."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))

    pm = ProjectMemory(str(mem_dir))
    _add_entry(pm, "entry-a", "user prefers short answers always concise brief")
    _add_entry(pm, "entry-b", "user prefers short answers always concise brief")

    before = _list_md_files(mem_dir)

    rc = main(["dream"])
    assert rc == 0

    after = _list_md_files(mem_dir)
    assert before == after, "dry-run must not modify the memory dir"


def test_dream_dryrun_empty_dir_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry-run on empty memory dir exits 0 with merged=0 pruned=0."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))

    rc = main(["dream"])
    assert rc == 0


# ---------------------------------------------------------------------------
# (b) --apply actually invokes DreamConsolidator and persists
# ---------------------------------------------------------------------------

def test_dream_apply_consolidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--apply runs consolidation; near-identical entries are deduplicated."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))

    pm = ProjectMemory(str(mem_dir))
    body = "user prefers short answers always concise brief clear fast"
    _add_entry(pm, "entry-x", body)
    _add_entry(pm, "entry-y", body)

    assert len(_list_md_files(mem_dir)) == 2

    rc = main(["dream", "--apply", "--force"])
    assert rc == 0

    # Deterministic dedup: one of the two near-identical entries was removed.
    assert len(_list_md_files(mem_dir)) == 1


def test_dream_apply_no_entries_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--apply on an empty memory dir exits 0 with merged=0 pruned=0."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))

    rc = main(["dream", "--apply", "--force"])
    assert rc == 0


# ---------------------------------------------------------------------------
# (c) --force bypasses a CLOSED M5 gate
# ---------------------------------------------------------------------------

def test_dream_force_bypasses_closed_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--force runs even when the time gate would block a normal --apply."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))

    # Install a fresh lock file — mtime = now, so time gate (≥ 24 h) is CLOSED.
    lock_path = mem_dir.parent / LOCK_FILE
    lock_path.write_text("", encoding="utf-8")
    t = time.time()
    os.utime(lock_path, (t, t))

    # Add two near-duplicate entries so we can confirm the dream ran.
    pm = ProjectMemory(str(mem_dir))
    body = "user prefers short answers always concise brief clear fast"
    _add_entry(pm, "force-a", body)
    _add_entry(pm, "force-b", body)

    rc = main(["dream", "--apply", "--force"])
    assert rc == 0

    # Dedup ran: one entry removed.
    assert len(_list_md_files(mem_dir)) == 1


# ---------------------------------------------------------------------------
# (d) closed gate without --force is a no-op exit 0
# ---------------------------------------------------------------------------

def test_dream_gate_closed_noop_exit_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --force, a gate-closed run exits 0 (a normal no-op)."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))

    # Fresh lock → time gate closed.
    lock_path = mem_dir.parent / LOCK_FILE
    lock_path.write_text("", encoding="utf-8")
    t = time.time()
    os.utime(lock_path, (t, t))

    pm = ProjectMemory(str(mem_dir))
    _add_entry(pm, "keep", "some memory entry body text here")

    before = _list_md_files(mem_dir)
    rc = main(["dream", "--apply"])
    assert rc == 0
    assert _list_md_files(mem_dir) == before, "gate-closed run must not remove entries"


# ---------------------------------------------------------------------------
# (e) bad dir → exit 2
# ---------------------------------------------------------------------------

def test_dream_bad_dir_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SIMPLE_AGENT_MEMORY_DIR pointing at a file (not a dir) exits 2."""
    bad_path = tmp_path / "not_a_dir"
    bad_path.write_text("I am a file", encoding="utf-8")
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(bad_path))

    rc = main(["dream"])
    assert rc == 2


def test_dream_bad_dir_exits_2_on_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same check for --apply mode."""
    bad_path = tmp_path / "not_a_dir"
    bad_path.write_text("I am a file", encoding="utf-8")
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(bad_path))

    rc = main(["dream", "--apply", "--force"])
    assert rc == 2


# ---------------------------------------------------------------------------
# (f) --provider openai constructs OpenAIProvider (mocked, no network)
# ---------------------------------------------------------------------------

def test_dream_provider_openai_constructs_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--provider openai constructs an OpenAIProvider; no real API call."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-fake")

    constructed: list[object] = []

    # Patch DreamConsolidator.__init__ to capture provider arg.
    original_init = DreamConsolidator.__init__

    def spy_init(
        self: DreamConsolidator, memory_dir: object, provider: object = None, **kw: object
    ) -> None:
        constructed.append(provider)
        original_init(self, memory_dir, provider=provider, **kw)

    monkeypatch.setattr(DreamConsolidator, "__init__", spy_init)

    # Also patch consolidate to avoid real work.
    monkeypatch.setattr(
        DreamConsolidator, "consolidate",
        lambda *a, **kw: DreamResult(merged=0, pruned=0, runs=0, written_paths=()),
    )

    rc = main(["dream", "--apply", "--force", "--provider", "openai"])
    assert rc == 0

    assert len(constructed) == 1
    from simple_coding_agent.provider import OpenAIProvider
    assert isinstance(constructed[0], OpenAIProvider), (
        f"Expected OpenAIProvider, got {type(constructed[0])}"
    )


def test_dream_provider_openai_default_model_is_qwen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--provider openai defaults to qwen-plus-latest (matches rest of codebase).

    Locks review-fix: previously defaulted to gpt-4o, which fails when only
    DASHSCOPE_API_KEY is set (DashScope endpoint does not serve gpt-4o). The
    rest of the replica (benchmarks/bench_openai_cost.py,
    benchmarks/bench_sm_compact_latency.py) targets qwen-plus-latest, so the
    dream subcommand now matches. OPENAI_MODEL env var still overrides.
    """
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-fake")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    constructed: list[object] = []
    original_init = DreamConsolidator.__init__

    def spy_init(
        self: DreamConsolidator, memory_dir: object, provider: object = None, **kw: object
    ) -> None:
        constructed.append(provider)
        original_init(self, memory_dir, provider=provider, **kw)

    monkeypatch.setattr(DreamConsolidator, "__init__", spy_init)
    monkeypatch.setattr(
        DreamConsolidator, "consolidate",
        lambda *a, **kw: DreamResult(merged=0, pruned=0, runs=0, written_paths=()),
    )

    rc = main(["dream", "--apply", "--force", "--provider", "openai"])
    assert rc == 0

    assert len(constructed) == 1
    provider = constructed[0]
    # OpenAIProvider stores the model on self._model
    assert getattr(provider, "_model", None) == "qwen-plus-latest"


def test_dream_provider_openai_model_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPENAI_MODEL env var overrides the default model in --provider openai."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setenv("SIMPLE_AGENT_MEMORY_DIR", str(mem_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-fake")
    monkeypatch.setenv("OPENAI_MODEL", "qwen-turbo")

    constructed: list[object] = []
    original_init = DreamConsolidator.__init__

    def spy_init(
        self: DreamConsolidator, memory_dir: object, provider: object = None, **kw: object
    ) -> None:
        constructed.append(provider)
        original_init(self, memory_dir, provider=provider, **kw)

    monkeypatch.setattr(DreamConsolidator, "__init__", spy_init)
    monkeypatch.setattr(
        DreamConsolidator, "consolidate",
        lambda *a, **kw: DreamResult(merged=0, pruned=0, runs=0, written_paths=()),
    )

    rc = main(["dream", "--apply", "--force", "--provider", "openai"])
    assert rc == 0

    assert len(constructed) == 1
    provider = constructed[0]
    assert getattr(provider, "_model", None) == "qwen-turbo"


# ---------------------------------------------------------------------------
# (g) MetricsCollector dream_runs / dream_merged / dream_pruned
# ---------------------------------------------------------------------------

def test_metrics_record_dream_run() -> None:
    """record_dream_run bumps all three counters."""
    m = MetricsCollector()
    assert m.dream_runs == 0
    assert m.dream_merged == 0
    assert m.dream_pruned == 0

    m.record_dream_run(merged=3, pruned=1)
    assert m.dream_runs == 1
    assert m.dream_merged == 3
    assert m.dream_pruned == 1

    m.record_dream_run(merged=0, pruned=2)
    assert m.dream_runs == 2
    assert m.dream_merged == 3
    assert m.dream_pruned == 3


def test_metrics_format_stats_includes_dream_counters() -> None:
    """format_stats() shows dream_runs, dream_merged, dream_pruned."""
    m = MetricsCollector()
    m.record_dream_run(merged=5, pruned=2)
    stats = m.format_stats()
    assert "dream_runs=1" in stats
    assert "dream_merged=5" in stats
    assert "dream_pruned=2" in stats


# ---------------------------------------------------------------------------
# (h) --dream-on-exit: OFF fires nothing, ON fires exactly once
# ---------------------------------------------------------------------------

def test_dream_on_exit_off_fires_no_dream(tmp_path: Path) -> None:
    """AgentLoop with dream_on_exit=False (default) fires no dream."""
    from simple_coding_agent.context import ContextBudget, ContextBuilder
    from simple_coding_agent.loop import AgentLoop
    from simple_coding_agent.provider import MockProvider
    from simple_coding_agent.tools import ToolExecutor, ToolRegistry
    from simple_coding_agent.transcript import Transcript

    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    pm = ProjectMemory(str(mem_dir))

    loop = AgentLoop(
        provider=MockProvider([]),
        tool_executor=ToolExecutor(ToolRegistry()),
        transcript=Transcript(),
        context_builder=ContextBuilder(
            budget=ContextBudget(max_tokens=4096, reserved_output_tokens=1024)
        ),
        budget=ContextBudget(max_tokens=4096, reserved_output_tokens=1024),
        project_memory=pm,
        dream_on_exit=False,
    )

    call_count = 0

    def fake_consolidate(*a: object, **kw: object) -> DreamResult:
        nonlocal call_count
        call_count += 1
        return DreamResult(merged=0, pruned=0, runs=0, written_paths=())

    with patch.object(DreamConsolidator, "consolidate", fake_consolidate):
        loop._run_dream_on_exit()

    assert call_count == 0


def test_dream_on_exit_on_fires_exactly_once(tmp_path: Path) -> None:
    """AgentLoop with dream_on_exit=True fires exactly one dream at /exit."""
    from simple_coding_agent.context import ContextBudget, ContextBuilder
    from simple_coding_agent.loop import AgentLoop
    from simple_coding_agent.provider import MockProvider
    from simple_coding_agent.tools import ToolExecutor, ToolRegistry
    from simple_coding_agent.transcript import Transcript

    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    pm = ProjectMemory(str(mem_dir))

    loop = AgentLoop(
        provider=MockProvider([]),
        tool_executor=ToolExecutor(ToolRegistry()),
        transcript=Transcript(),
        context_builder=ContextBuilder(
            budget=ContextBudget(max_tokens=4096, reserved_output_tokens=1024)
        ),
        budget=ContextBudget(max_tokens=4096, reserved_output_tokens=1024),
        project_memory=pm,
        dream_on_exit=True,
    )

    call_count = 0

    def fake_consolidate(*a: object, **kw: object) -> DreamResult:
        nonlocal call_count
        call_count += 1
        return DreamResult(merged=0, pruned=0, runs=0, written_paths=())

    with patch.object(DreamConsolidator, "consolidate", fake_consolidate):
        loop._run_dream_on_exit()
        # Second call should NOT fire again (one-shot).
        loop._run_dream_on_exit()

    assert call_count == 1, f"Expected exactly 1 dream, got {call_count}"
