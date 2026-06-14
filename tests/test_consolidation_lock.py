"""Tests for consolidation_lock.py — dream gate cascade (M5 D1).

TDD: every test is written BEFORE the implementation exists.
Timestamps are fully injected via os.utime + monkeypatch — no real sleep.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from simple_coding_agent.consolidation_lock import (
    list_sessions_touched_since,
    read_last_consolidated_at,
    rollback_consolidation_lock,
    should_dream,
    try_acquire_consolidation_lock,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HOUR_MS = 3_600_000.0  # ms per hour
DAY_MS = 24 * HOUR_MS


def _stamp(path: Path, mtime_ms: float) -> None:
    """Set file mtime via os.utime (seconds; filesystem rounds sub-second)."""
    t = mtime_ms / 1000.0
    os.utime(path, (t, t))


def _create_sessions(sessions_dir: Path, count: int, mtime_ms: float) -> list[str]:
    """Create ``count`` *.json session files with given mtime. Returns stems."""
    stems: list[str] = []
    for i in range(count):
        stem = f"session-{i:03d}"
        p = sessions_dir / f"{stem}.json"
        p.write_text("{}")
        _stamp(p, mtime_ms)
        stems.append(stem)
    return stems


# ---------------------------------------------------------------------------
# read_last_consolidated_at — consolidationLock.ts:29
# ---------------------------------------------------------------------------


def test_read_last_consolidated_at_absent(tmp_path: Path) -> None:
    """Missing lock file → 0."""
    lock = tmp_path / ".consolidate-lock"
    assert read_last_consolidated_at(lock) == 0.0


def test_read_last_consolidated_at_mtime_roundtrip(tmp_path: Path) -> None:
    """mtime == lastConsolidatedAt round-trip through os.utime + stat.

    Covers exit-gate requirement: 'mtime==lastConsolidatedAt round-trip'.
    """
    lock = tmp_path / ".consolidate-lock"
    lock.write_text("12345")
    now_ms = time.time() * 1000.0
    target_ms = now_ms - 25 * HOUR_MS
    _stamp(lock, target_ms)
    result = read_last_consolidated_at(lock)
    # Allow ±1 second for filesystem rounding on macOS/Linux
    assert abs(result - target_ms) < 1000.0, f"mtime mismatch: {result} vs {target_ms}"


# ---------------------------------------------------------------------------
# list_sessions_touched_since — consolidationLock.ts:118
# ---------------------------------------------------------------------------


def test_list_sessions_touched_since_empty_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty sessions directory → empty list."""
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    assert list_sessions_touched_since(since_ms=0.0) == []


def test_list_sessions_touched_since_filters_by_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only sessions with mtime > since_ms are returned."""
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    now_ms = time.time() * 1000.0
    old_ms = now_ms - 48 * HOUR_MS
    new_ms = now_ms - 1 * HOUR_MS
    _create_sessions(tmp_path, 3, old_ms)
    new_stems = _create_sessions(tmp_path, 4, new_ms)
    since_ms = now_ms - 24 * HOUR_MS
    result = list_sessions_touched_since(since_ms=since_ms)
    assert sorted(result) == sorted(new_stems)


def test_list_sessions_touched_since_excludes_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exclude_id removes the matching stem from the result."""
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    now_ms = time.time() * 1000.0
    stems = _create_sessions(tmp_path, 5, now_ms - 1_000)
    result = list_sessions_touched_since(since_ms=0.0, exclude_id=stems[0])
    assert stems[0] not in result
    assert len(result) == 4


# ---------------------------------------------------------------------------
# try_acquire_consolidation_lock — consolidationLock.ts:46
# ---------------------------------------------------------------------------


def test_acquire_no_prior_lock(tmp_path: Path) -> None:
    """No prior file → acquires, writes our PID, returns 0 (no prior mtime)."""
    lock = tmp_path / ".consolidate-lock"
    result = try_acquire_consolidation_lock(lock, pid=os.getpid())
    assert result == 0.0
    assert lock.exists()
    assert lock.read_text().strip() == str(os.getpid())


def test_acquire_stale_lock_reclaims(tmp_path: Path) -> None:
    """Lock older than HOLDER_STALE_MS → reclaim regardless of PID liveness.

    Covers exit-gate requirement: 'acquire returns prior mtime'.
    """
    lock = tmp_path / ".consolidate-lock"
    lock.write_text("999999999")  # dead PID
    now_ms = time.time() * 1000.0
    old_mtime_ms = now_ms - 2 * HOUR_MS  # 2h ago > HOLDER_STALE_MS (1h)
    _stamp(lock, old_mtime_ms)

    result = try_acquire_consolidation_lock(
        lock,
        pid=os.getpid(),
        now_ms=now_ms,
        is_process_running_fn=lambda _pid: False,
    )
    assert result is not None
    assert abs(result - old_mtime_ms) < 1000.0


def test_acquire_blocked_by_live_pid(tmp_path: Path) -> None:
    """Fresh lock (<HOLDER_STALE_MS) held by live PID → returns None.

    Covers exit-gate requirement: 'acquire returns None when held'.
    """
    lock = tmp_path / ".consolidate-lock"
    holder_pid = os.getpid()
    lock.write_text(str(holder_pid))
    now_ms = time.time() * 1000.0
    fresh_ms = now_ms - 30 * 60 * 1000  # 30 min < 1h
    _stamp(lock, fresh_ms)

    result = try_acquire_consolidation_lock(
        lock,
        pid=holder_pid + 1,  # a different "us"
        now_ms=now_ms,
        is_process_running_fn=lambda _pid: True,  # holder is live
    )
    assert result is None


# ---------------------------------------------------------------------------
# rollback_consolidation_lock — consolidationLock.ts:91
# ---------------------------------------------------------------------------


def test_rollback_rewinds_mtime(tmp_path: Path) -> None:
    """rollback clears PID body and rewinds mtime to prior_mtime.

    Covers exit-gate requirement: 'rollback rewinds mtime so time gate re-opens'.
    """
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    prior_mtime_ms = now_ms - 25 * HOUR_MS
    lock.write_text(str(os.getpid()))
    _stamp(lock, now_ms)  # mtime = now (after acquire)

    rollback_consolidation_lock(lock, prior_mtime_ms)

    assert lock.read_text() == ""
    result = read_last_consolidated_at(lock)
    assert abs(result - prior_mtime_ms) < 1000.0


def test_rollback_prior_zero_unlinks(tmp_path: Path) -> None:
    """prior_mtime=0 → unlink (restore no-file state)."""
    lock = tmp_path / ".consolidate-lock"
    lock.write_text(str(os.getpid()))
    rollback_consolidation_lock(lock, prior_mtime=0.0)
    assert not lock.exists()


# ---------------------------------------------------------------------------
# should_dream — full gate cascade, autoDream.ts:125-189
# ---------------------------------------------------------------------------


def test_should_dream_all_gates_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All gates open → should_dream=True, prior_mtime is set for rollback."""
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    old_ms = now_ms - 25 * HOUR_MS
    lock.write_text("")
    _stamp(lock, old_ms)
    _create_sessions(tmp_path, 5, now_ms - 1 * HOUR_MS)

    decision = should_dream(
        lock_path=lock,
        sessions_dir=tmp_path,
        enabled=True,
        now_ms=now_ms,
        last_scan_at_ms=0.0,
        min_hours=24,
        min_sessions=5,
        pid=os.getpid(),
        is_process_running_fn=lambda _pid: False,
    )
    assert decision.should_dream is True
    assert decision.prior_mtime is not None


def test_should_dream_time_gate_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Time gate closed (lock mtime < 24h ago) → should_dream=False.

    Covers exit-gate requirement: 'time-gate closed'.
    """
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    recent_ms = now_ms - 2 * HOUR_MS  # only 2h ago
    lock.write_text("")
    _stamp(lock, recent_ms)
    _create_sessions(tmp_path, 5, now_ms - 1 * HOUR_MS)

    decision = should_dream(
        lock_path=lock,
        sessions_dir=tmp_path,
        enabled=True,
        now_ms=now_ms,
        last_scan_at_ms=0.0,
    )
    assert decision.should_dream is False


def test_should_dream_session_gate_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """< MIN_SESSIONS sessions → should_dream=False.

    Covers exit-gate requirement: 'session-gate count' (failure path).
    """
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    old_ms = now_ms - 25 * HOUR_MS
    lock.write_text("")
    _stamp(lock, old_ms)
    _create_sessions(tmp_path, 3, now_ms - 1 * HOUR_MS)  # < 5

    decision = should_dream(
        lock_path=lock,
        sessions_dir=tmp_path,
        enabled=True,
        now_ms=now_ms,
        last_scan_at_ms=0.0,
    )
    assert decision.should_dream is False


def test_should_dream_current_session_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current session excluded; 5 others remain → session gate passes.

    Covers exit-gate requirement: 'current-session exclusion'.
    """
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    old_ms = now_ms - 25 * HOUR_MS
    lock.write_text("")
    _stamp(lock, old_ms)
    stems = _create_sessions(tmp_path, 6, now_ms - 1 * HOUR_MS)
    current_id = stems[0]  # will be excluded → 5 remain

    decision = should_dream(
        lock_path=lock,
        sessions_dir=tmp_path,
        enabled=True,
        now_ms=now_ms,
        last_scan_at_ms=0.0,
        current_session_id=current_id,
        min_sessions=5,
        pid=os.getpid(),
        is_process_running_fn=lambda _pid: False,
    )
    assert decision.should_dream is True


def test_should_dream_only_current_session_no_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1 session exists but it's the current one → count=0 < MIN_SESSIONS."""
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    old_ms = now_ms - 25 * HOUR_MS
    lock.write_text("")
    _stamp(lock, old_ms)
    stems = _create_sessions(tmp_path, 1, now_ms - 1 * HOUR_MS)

    decision = should_dream(
        lock_path=lock,
        sessions_dir=tmp_path,
        enabled=True,
        now_ms=now_ms,
        last_scan_at_ms=0.0,
        current_session_id=stems[0],
    )
    assert decision.should_dream is False


def test_should_dream_scan_throttle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """last_scan_at_ms < SESSION_SCAN_INTERVAL_MS ago → throttle blocks.

    Covers exit-gate requirement: 'scan-throttle'.
    """
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    old_ms = now_ms - 25 * HOUR_MS
    lock.write_text("")
    _stamp(lock, old_ms)
    _create_sessions(tmp_path, 5, now_ms - 1 * HOUR_MS)

    # Last scan was 5 min ago (< 10-min throttle)
    last_scan_ms = now_ms - 5 * 60 * 1000.0

    decision = should_dream(
        lock_path=lock,
        sessions_dir=tmp_path,
        enabled=True,
        now_ms=now_ms,
        last_scan_at_ms=last_scan_ms,
    )
    assert decision.should_dream is False


def test_should_dream_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """enabled=False → should_dream=False regardless of other gates."""
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    old_ms = now_ms - 25 * HOUR_MS
    lock.write_text("")
    _stamp(lock, old_ms)
    _create_sessions(tmp_path, 5, now_ms - 1 * HOUR_MS)

    decision = should_dream(
        lock_path=lock,
        sessions_dir=tmp_path,
        enabled=False,
        now_ms=now_ms,
        last_scan_at_ms=0.0,
    )
    assert decision.should_dream is False


def test_should_dream_returns_sessions_since(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When should_dream=True, sessions_since carries the counted session stems."""
    monkeypatch.setenv("SIMPLE_AGENT_SESSIONS_DIR", str(tmp_path))
    lock = tmp_path / ".consolidate-lock"
    now_ms = time.time() * 1000.0
    old_ms = now_ms - 25 * HOUR_MS
    lock.write_text("")
    _stamp(lock, old_ms)
    stems = _create_sessions(tmp_path, 5, now_ms - 1 * HOUR_MS)

    decision = should_dream(
        lock_path=lock,
        sessions_dir=tmp_path,
        enabled=True,
        now_ms=now_ms,
        last_scan_at_ms=0.0,
        pid=os.getpid(),
        is_process_running_fn=lambda _pid: False,
    )
    assert decision.should_dream is True
    assert sorted(decision.sessions_since) == sorted(stems)
