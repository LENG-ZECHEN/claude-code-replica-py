"""M5-D1: lock + gate cascade for dream consolidation.

Replicates the cheapest-first gate cascade from the TS auto-dream service:
  autoDream.ts:125-189  (gate order: enabled → time → scan-throttle → session → lock)
  consolidationLock.ts  (lock file semantics, all five functions)

Replica divergences from TS (documented here and in HANDOFF.md § M5):

1. **"Sessions touched since" maps to replica session layout.**
   TS scans per-cwd JSONL transcripts via ``getProjectDir + listCandidates``
   (consolidationLock.ts:118). The replica counts ``*.json`` session files
   under ``resolve_sessions_dir()`` (honoring ``SIMPLE_AGENT_SESSIONS_DIR``),
   filtering by file mtime > ``since_ms``. Intentional substitution —
   the replica's session_store layout uses JSON files, not JSONL transcripts.
   Use ``resolve_sessions_dir()`` from ``session_store.py``; do NOT re-derive
   the directory or read the env var twice.

2. **No GrowthBook flags.** TS reads ``tengu_onyx_plover`` for minHours /
   minSessions (autoDream.ts:73-93). The replica uses documented defaults as
   module constants (``MIN_HOURS = 24``, ``MIN_SESSIONS = 5``), optionally
   overridable by keyword args so M7's ``--force`` and tests can tune them.
   Mirrors how the replica replaces every other GB flag with a local constant.

3. **No async.** TS ``tryAcquireConsolidationLock`` is ``async`` with
   ``Promise.all([stat, readFile])``. The replica is synchronous
   ``os.stat + Path.read_text`` — same logic, no ``await``. Consistent with
   synchronous sideQuery recall and synchronous stop-hook fold.

4. **Scan throttle is injected as ``last_scan_at_ms`` parameter.**
   TS carries ``lastSessionScanAt`` inside the ``initAutoDream()`` closure
   (autoDream.ts:123), reset per test via ``initAutoDream()`` in beforeEach.
   The replica has no async startup closure; callers inject the scan-throttle
   state as an explicit argument so tests control it without module globals.

Source mapping:
  consolidationLock.ts:16   LOCK_FILE = '.consolidate-lock'
  consolidationLock.ts:19   HOLDER_STALE_MS = 60 * 60 * 1000
  autoDream.ts:64           MIN_HOURS (DEFAULTS.minHours) = 24
  autoDream.ts:65           MIN_SESSIONS (DEFAULTS.minSessions) = 5
  autoDream.ts:56           SESSION_SCAN_INTERVAL_MS = 10 * 60 * 1000
  consolidationLock.ts:29   readLastConsolidatedAt
  consolidationLock.ts:46   tryAcquireConsolidationLock
  consolidationLock.ts:91   rollbackConsolidationLock
  consolidationLock.ts:118  listSessionsTouchedSince
  autoDream.ts:125          runAutoDream gate order
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .session_store import resolve_sessions_dir

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

LOCK_FILE = ".consolidate-lock"  # consolidationLock.ts:16
HOLDER_STALE_MS: float = 60 * 60 * 1000  # 1 h; consolidationLock.ts:19
MIN_HOURS: float = 24.0  # autoDream.ts:64
MIN_SESSIONS: int = 5  # autoDream.ts:65
SESSION_SCAN_INTERVAL_MS: float = 10 * 60 * 1000  # 10 min; autoDream.ts:56


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DreamGateDecision:
    """Result of the full gate cascade (should_dream + rollback data).

    When ``should_dream=True`` the lock is already held. The caller MUST call
    ``rollback_consolidation_lock(lock_path, prior_mtime)`` if the dream fails.
    ``sessions_since`` is ready to pass to the dream prompt.
    """

    should_dream: bool
    prior_mtime: float | None  # set only when should_dream=True
    sessions_since: tuple[str, ...]  # empty when should_dream=False


# ---------------------------------------------------------------------------
# read_last_consolidated_at — consolidationLock.ts:29
# ---------------------------------------------------------------------------


def read_last_consolidated_at(lock_path: Path | str) -> float:
    """mtime of lock_path in milliseconds, or 0.0 if absent. One stat.

    consolidationLock.ts:29:
        ``const s = await stat(lockPath()); return s.mtimeMs``
        ``catch { return 0 }``
    """
    try:
        s = os.stat(lock_path)
        return s.st_mtime * 1000.0
    except OSError:  # ENOENT or permission error — treated as no prior lock
        return 0.0


# ---------------------------------------------------------------------------
# list_sessions_touched_since — consolidationLock.ts:118
# ---------------------------------------------------------------------------


def list_sessions_touched_since(
    since_ms: float,
    *,
    sessions_dir: Path | str | None = None,
    exclude_id: str | None = None,
) -> list[str]:
    """Return session stems whose *.json mtime > ``since_ms``.

    Replica divergence from consolidationLock.ts:118 (see module docstring
    item 1): scans ``*.json`` under ``resolve_sessions_dir()`` instead of
    TS's per-cwd JSONL transcripts.

    Uses mtime (sessions TOUCHED since), not ctime/birthtime — mirrors TS:
    "Uses mtime (sessions TOUCHED since), not birthtime (0 on ext4)."

    ``exclude_id`` lets the caller pass the current session stem so it does
    not count toward the ≥5 threshold (autoDream.ts:163-165).
    """
    sdir = Path(sessions_dir) if sessions_dir is not None else resolve_sessions_dir()
    if not sdir.exists():
        return []
    results: list[str] = []
    for p in sdir.glob("*.json"):
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_mtime * 1000.0 <= since_ms:
            continue
        stem = p.stem
        if stem == exclude_id:
            continue
        results.append(stem)
    return results


# ---------------------------------------------------------------------------
# try_acquire_consolidation_lock — consolidationLock.ts:46
# ---------------------------------------------------------------------------


def _is_process_running(pid: int) -> bool:
    """True if ``pid`` is alive (os.kill(pid, 0) succeeds)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def try_acquire_consolidation_lock(
    lock_path: Path | str,
    *,
    now_ms: float | None = None,
    pid: int | None = None,
    is_process_running_fn: Callable[[int], bool] | None = None,
) -> float | None:
    """Write our PID to lock_path and return the pre-acquire mtime (ms).

    Returns ``None`` when blocked by a live holder whose lock is still fresh
    (< HOLDER_STALE_MS).  Returns ``0.0`` when there was no prior lock file.

    consolidationLock.ts:46:
      - Read existing stat + body (ENOENT → no prior lock).
      - If lock age < HOLDER_STALE_MS AND body is a live PID → null.
      - Otherwise reclaim: write our PID, verify we won the last-write race.
      - Return pre-acquire mtime (or 0 if no prior file) for rollback.
    """
    now = now_ms if now_ms is not None else time.time() * 1000.0
    our_pid = pid if pid is not None else os.getpid()
    check_alive = (
        is_process_running_fn if is_process_running_fn is not None else _is_process_running
    )
    path = Path(lock_path)

    mtime_ms: float | None = None
    holder_pid: int | None = None
    try:
        s = os.stat(path)
        mtime_ms = s.st_mtime * 1000.0
        raw = path.read_text(encoding="utf-8")
        holder_pid = int(raw.strip())
    except OSError:
        # ENOENT or permission error — no prior lock (ts:57 ``catch { // ENOENT }``).
        pass
    except ValueError:
        # Unparseable PID body — treat as dead holder (ts:54-55).
        pass

    if mtime_ms is not None and (now - mtime_ms) < HOLDER_STALE_MS:
        if holder_pid is not None and check_alive(holder_pid):
            # Fresh lock held by live PID → blocked (ts:60-65).
            return None
        # Dead PID or unparseable body within staleness window — reclaim (ts:67).

    # Write our PID (ts:72).
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(our_pid), encoding="utf-8")

    # Verify we won the last-write race (ts:75-81).
    try:
        verify = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        if int(verify.strip()) != our_pid:
            return None
    except ValueError:
        return None

    return mtime_ms if mtime_ms is not None else 0.0


# ---------------------------------------------------------------------------
# rollback_consolidation_lock — consolidationLock.ts:91
# ---------------------------------------------------------------------------


def rollback_consolidation_lock(lock_path: Path | str, prior_mtime: float) -> None:
    """Rewind the lock mtime to ``prior_mtime`` after a failed dream.

    Clears the PID body so our still-running process does not look like a
    holder while the next eligible turn arrives. ``prior_mtime == 0.0``
    means there was no prior file: unlink to restore the no-file state.

    consolidationLock.ts:91:
        ``await writeFile(path, '')``
        ``const t = priorMtime / 1000; await utimes(path, t, t)``
        ``priorMtime === 0 → await unlink(path)``
    Best-effort: OSError is swallowed (ts:103-107 logs then returns).
    """
    path = Path(lock_path)
    try:
        if prior_mtime == 0.0:
            path.unlink(missing_ok=True)  # ts:96-98
            return
        path.write_text("", encoding="utf-8")
        t = prior_mtime / 1000.0  # utimes wants seconds (ts:101)
        os.utime(path, (t, t))
    except OSError:
        # Best-effort rollback (ts:103-107: log + return, never raise).
        pass


# ---------------------------------------------------------------------------
# should_dream — full gate cascade, autoDream.ts:125-189
# ---------------------------------------------------------------------------

_NO_DREAM = DreamGateDecision(should_dream=False, prior_mtime=None, sessions_since=())


def should_dream(
    lock_path: Path | str,
    sessions_dir: Path | str | None = None,
    *,
    enabled: bool = True,
    now_ms: float,
    last_scan_at_ms: float = 0.0,
    current_session_id: str | None = None,
    min_hours: float = MIN_HOURS,
    min_sessions: int = MIN_SESSIONS,
    pid: int | None = None,
    is_process_running_fn: Callable[[int], bool] | None = None,
) -> DreamGateDecision:
    """Full cheapest-first gate cascade.

    Gate order (autoDream.ts:125-189):
      1. enabled check (isGateOpen analog) → bail if False
      2. time gate: hours since lock mtime >= min_hours (one stat; ts:140-141)
      3. scan throttle: last_scan_at_ms < SESSION_SCAN_INTERVAL_MS ago → bail
         (ts:144-150; injected rather than closure-scoped — see module doc)
      4. session gate: sessions touched since lastConsolidatedAt >= min_sessions
         after excluding current_session_id (ts:155-171)
      5. lock: try_acquire_consolidation_lock (ts:182-189)

    Returns ``DreamGateDecision(should_dream=True, prior_mtime=..., ...)``
    when all gates pass AND the lock is acquired.  The caller must call
    ``rollback_consolidation_lock(lock_path, decision.prior_mtime)`` on
    dream failure.
    """
    # Gate 1: enabled (autoDream.ts:129 isGateOpen)
    if not enabled:
        return _NO_DREAM

    # Gate 2: time gate (autoDream.ts:140-141)
    last_at_ms = read_last_consolidated_at(lock_path)
    hours_since = (now_ms - last_at_ms) / 3_600_000.0
    if hours_since < min_hours:
        return _NO_DREAM

    # Gate 3: scan throttle (autoDream.ts:144-150)
    if (now_ms - last_scan_at_ms) < SESSION_SCAN_INTERVAL_MS:
        return _NO_DREAM

    # Gate 4: session gate (autoDream.ts:155-171)
    session_ids = list_sessions_touched_since(
        last_at_ms,
        sessions_dir=sessions_dir,
        exclude_id=current_session_id,
    )
    if len(session_ids) < min_sessions:
        return _NO_DREAM

    # Gate 5: lock (autoDream.ts:182-189)
    prior_mtime = try_acquire_consolidation_lock(
        lock_path,
        now_ms=now_ms,
        pid=pid,
        is_process_running_fn=is_process_running_fn,
    )
    if prior_mtime is None:
        return _NO_DREAM

    return DreamGateDecision(
        should_dream=True,
        prior_mtime=prior_mtime,
        sessions_since=tuple(session_ids),
    )


__all__ = [
    "HOLDER_STALE_MS",
    "LOCK_FILE",
    "MIN_HOURS",
    "MIN_SESSIONS",
    "SESSION_SCAN_INTERVAL_MS",
    "DreamGateDecision",
    "list_sessions_touched_since",
    "read_last_consolidated_at",
    "rollback_consolidation_lock",
    "should_dream",
    "try_acquire_consolidation_lock",
]
