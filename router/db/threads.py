"""Thread creation writes for the single-writer router."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from router.db import gates, writes
from router.db.transaction import run_immediate
from router.errors import AcceptError

_THREAD_COLS = (
    "thread_id, status, status_reason, baton, last_turn_id, workspace_id, created_at"
)
_CLEAR_BATON_STATUSES = frozenset({"done", "cancelled"})
_HALT_STATUSES = frozenset({"done", "needs_human", "blocked", "cancelled"})
_STATUS_REASONS = frozenset(
    {
        "recovery_required",
        "disconnected",
        "invalid_submission",
        "stale_read",
        "auth_failure",
        "user_cancelled",
        "projection_error",
        "port_conflict",
    }
)


def create_thread(
    conn: sqlite3.Connection, thread_id: str, workspace_id: str, baton: str
) -> dict:
    """Create one active thread and return its public state."""
    now = datetime.now(timezone.utc).isoformat()
    return run_immediate(conn, lambda: _insert_thread(conn, thread_id, workspace_id, baton, now))


def _insert_thread(
    conn: sqlite3.Connection, thread_id: str, workspace_id: str, baton: str, now: str
) -> dict:
    """Insert the thread row, mapping duplicate ids to structured errors."""
    try:
        conn.execute(
            "INSERT INTO threads(thread_id, status, status_reason, baton, last_turn_id, "
            "workspace_id, created_at) VALUES(?,'active',NULL,?,0,?,?)",
            (thread_id, baton, workspace_id, now),
        )
    except sqlite3.IntegrityError as exc:
        raise AcceptError("thread_exists", 409) from exc
    return _fetch_thread(conn, thread_id)


def _fetch_thread(conn: sqlite3.Connection, thread_id: str) -> dict:
    """Return the created thread row as a response dict."""
    row = conn.execute(
        f"SELECT {_THREAD_COLS} FROM threads WHERE thread_id=?", (thread_id,)
    ).fetchone()
    return dict(row)


def validate_status_update(status: str, status_reason: str | None) -> tuple[str, str | None]:
    """Return a schema-coherent halt status pair or raise a structured error."""
    if status not in _HALT_STATUSES:
        raise AcceptError("invalid_status", 400)
    if status == "done":
        if status_reason is not None:
            raise AcceptError("invalid_status", 400)
        return status, None
    if status_reason is None:
        raise AcceptError("reason_required", 400)
    if status_reason not in _STATUS_REASONS:
        raise AcceptError("invalid_status", 400)
    return status, status_reason


def set_thread_status(
    conn: sqlite3.Connection,
    thread_id: str,
    agent: str,
    status: str,
    status_reason: str | None,
) -> dict:
    """Atomically move an active thread to a terminal or paused status."""
    now = datetime.now(timezone.utc).isoformat()
    return run_immediate(
        conn, lambda: _set_thread_status(conn, thread_id, agent, status, status_reason, now)
    )


def _set_thread_status(
    conn: sqlite3.Connection,
    thread_id: str,
    agent: str,
    status: str,
    status_reason: str | None,
    now: str,
) -> dict:
    """Gate on current baton/lease, update status, mark projections dirty."""
    status, status_reason = validate_status_update(status, status_reason)
    thread = gates.load_active_thread(conn, thread_id)
    gates.check_baton(thread, agent)
    gates.check_lease(conn, thread_id, agent, now)
    baton = None if status in _CLEAR_BATON_STATUSES else thread["baton"]
    _update_status(conn, thread_id, status, status_reason, baton)
    writes.mark_dirty(conn, thread_id)
    return _fetch_thread(conn, thread_id)


def _update_status(
    conn: sqlite3.Connection,
    thread_id: str,
    status: str,
    status_reason: str | None,
    baton: str | None,
) -> None:
    """Update only an active row; raise if a concurrent state change won."""
    cur = conn.execute(
        "UPDATE threads SET status=?, status_reason=?, baton=? "
        "WHERE thread_id=? AND status='active'",
        (status, status_reason, baton, thread_id),
    )
    if cur.rowcount != 1:
        raise AcceptError("not_active", 409)
