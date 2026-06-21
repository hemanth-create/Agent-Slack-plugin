"""Dedicated lease expiry sweep for disconnected-thread detection."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from router.db.transaction import run_immediate


def _iso(dt: datetime) -> str:
    """Return the UTC ISO timestamp used by lease comparisons."""
    return dt.astimezone(timezone.utc).isoformat()


def sweep_expired_leases(conn: sqlite3.Connection, now: str | None = None) -> dict:
    """Expire overdue leases and mark abandoned active threads disconnected."""
    return run_immediate(conn, lambda: _sweep_expired_leases(conn, now))


def _sweep_expired_leases(conn: sqlite3.Connection, now: str | None) -> dict:
    """Run the sweep body inside the caller's transaction."""
    stamp = now or _iso(datetime.now(timezone.utc))
    thread_ids = _overdue_thread_ids(conn, stamp)
    expired = _expire_overdue(conn, stamp)
    disconnected = _disconnect_abandoned_threads(conn, thread_ids, stamp)
    return {"expired_leases": expired, "threads_disconnected": disconnected}


def _overdue_thread_ids(conn: sqlite3.Connection, stamp: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT thread_id FROM leases WHERE status='active' AND expires_at<=?",
        (stamp,),
    ).fetchall()
    return [str(row["thread_id"]) for row in rows]


def _expire_overdue(conn: sqlite3.Connection, stamp: str) -> int:
    cur = conn.execute(
        "UPDATE leases SET status='expired' WHERE status='active' AND expires_at<=?",
        (stamp,),
    )
    return int(cur.rowcount)


def _disconnect_abandoned_threads(
    conn: sqlite3.Connection, thread_ids: list[str], stamp: str
) -> int:
    disconnected = 0
    for thread_id in thread_ids:
        if _active_lease(conn, thread_id, stamp) is None:
            disconnected += _mark_disconnected(conn, thread_id)
    return disconnected


def _active_lease(conn: sqlite3.Connection, thread_id: str, stamp: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT 1 FROM leases WHERE thread_id=? AND status='active' "
        "AND expires_at>? LIMIT 1",
        (thread_id, stamp),
    ).fetchone()


def _mark_disconnected(conn: sqlite3.Connection, thread_id: str) -> int:
    cur = conn.execute(
        "UPDATE threads SET status='needs_human', status_reason='disconnected' "
        "WHERE thread_id=? AND status='active'",
        (thread_id,),
    )
    return int(cur.rowcount)
