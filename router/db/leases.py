"""Lease lifecycle writes for compose ownership and expiry handling."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from router.db.transaction import run_immediate
from router.errors import AcceptError


def _iso(dt: datetime) -> str:
    """Return the UTC ISO timestamp used by lease comparisons."""
    return dt.astimezone(timezone.utc).isoformat()


def _load_active_thread(conn: sqlite3.Connection, thread_id: str) -> None:
    """Raise unless the thread exists and can accept active lease work."""
    row = conn.execute(
        "SELECT status, status_reason FROM threads WHERE thread_id=?", (thread_id,)
    ).fetchone()
    if row is None:
        raise AcceptError("thread_not_found", 404)
    if row["status"] != "active":
        raise AcceptError(row["status_reason"] or "not_active", 409)


def _fetch_lease(conn: sqlite3.Connection, lease_id: str) -> dict:
    """Return one lease row as a response dict."""
    row = conn.execute(
        "SELECT lease_id, thread_id, agent, acquired_at, expires_at, heartbeat_at, status "
        "FROM leases WHERE lease_id=?",
        (lease_id,),
    ).fetchone()
    return dict(row)


def acquire_lease(
    conn: sqlite3.Connection, agent: str, thread_id: str, ttl_seconds: int
) -> dict:
    """Acquire or extend this agent's active lease for a thread."""
    return run_immediate(conn, lambda: _acquire_lease(conn, agent, thread_id, ttl_seconds))


def _acquire_lease(
    conn: sqlite3.Connection, agent: str, thread_id: str, ttl_seconds: int
) -> dict:
    """Acquire or extend without sweeping other threads."""
    now_dt = datetime.now(timezone.utc)
    now = _iso(now_dt)
    _load_active_thread(conn, thread_id)
    current = _active_lease(conn, thread_id, now)
    expires = _iso(now_dt + timedelta(seconds=ttl_seconds))
    if current is not None and current["agent"] != agent:
        raise AcceptError("lease_conflict", 409)
    if current is not None:
        return _extend_lease(conn, current["lease_id"], now, expires)
    return _insert_lease(conn, agent, thread_id, now, expires)


def _extend_lease(conn: sqlite3.Connection, lease_id: str, now: str, expires: str) -> dict:
    """Extend an existing active lease and return it."""
    conn.execute(
        "UPDATE leases SET expires_at=?, heartbeat_at=? WHERE lease_id=?",
        (expires, now, lease_id),
    )
    return _fetch_lease(conn, lease_id)


def _insert_lease(
    conn: sqlite3.Connection, agent: str, thread_id: str, now: str, expires: str
) -> dict:
    """Insert and return a new active lease."""
    lease_id = uuid4().hex
    conn.execute(
        "INSERT INTO leases(lease_id, thread_id, agent, acquired_at, expires_at, heartbeat_at, status) "
        "VALUES(?,?,?,?,?,?,'active')",
        (lease_id, thread_id, agent, now, expires, now),
    )
    return _fetch_lease(conn, lease_id)


def _active_lease(conn: sqlite3.Connection, thread_id: str, now: str) -> sqlite3.Row | None:
    """Return the current unexpired active lease for a thread, if any."""
    return conn.execute(
        "SELECT lease_id, agent FROM leases WHERE thread_id=? AND status='active' "
        "AND expires_at>? ORDER BY expires_at DESC LIMIT 1",
        (thread_id, now),
    ).fetchone()


def renew_lease(
    conn: sqlite3.Connection, agent: str, thread_id: str, lease_id: str, ttl_seconds: int
) -> dict:
    """Heartbeat and extend an active lease owned by the authenticated agent."""
    return run_immediate(conn, lambda: _renew_lease(conn, agent, thread_id, lease_id, ttl_seconds))


def _renew_lease(
    conn: sqlite3.Connection, agent: str, thread_id: str, lease_id: str, ttl_seconds: int
) -> dict:
    """Renew without sweeping or changing thread status."""
    now_dt = datetime.now(timezone.utc)
    now = _iso(now_dt)
    _load_active_thread(conn, thread_id)
    _require_owned_active(conn, agent, thread_id, lease_id, now)
    expires = _iso(now_dt + timedelta(seconds=ttl_seconds))
    conn.execute(
        "UPDATE leases SET expires_at=?, heartbeat_at=? WHERE lease_id=?",
        (expires, now, lease_id),
    )
    return _fetch_lease(conn, lease_id)


def release_lease(conn: sqlite3.Connection, agent: str, thread_id: str, lease_id: str) -> dict:
    """Release an active lease owned by the authenticated agent."""
    return run_immediate(conn, lambda: _release_lease(conn, agent, thread_id, lease_id))


def _release_lease(conn: sqlite3.Connection, agent: str, thread_id: str, lease_id: str) -> dict:
    """Release without sweeping or changing thread status."""
    now = _iso(datetime.now(timezone.utc))
    _require_owned_active(conn, agent, thread_id, lease_id, now)
    conn.execute("UPDATE leases SET status='released' WHERE lease_id=?", (lease_id,))
    return _fetch_lease(conn, lease_id)


def _require_owned_active(
    conn: sqlite3.Connection, agent: str, thread_id: str, lease_id: str, now: str
) -> None:
    """Raise unless lease_id is active, unexpired, and owned by agent."""
    row = conn.execute(
        "SELECT 1 FROM leases WHERE lease_id=? AND thread_id=? AND agent=? "
        "AND status='active' AND expires_at>?",
        (lease_id, thread_id, agent, now),
    ).fetchone()
    if row is None:
        raise AcceptError("lease_not_active", 409)
