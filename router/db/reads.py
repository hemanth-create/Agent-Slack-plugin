"""Read-only queries against router.db (no writes here; SQL stays under db/)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from router.db.connection import connect

_THREAD_COLS = (
    "thread_id, status, status_reason, baton, last_turn_id, workspace_id, created_at"
)
_EVENT_COLS = "id, thread_id, author, reply_to, ts, body"


def read_thread(db_path: Path, thread_id: str) -> sqlite3.Row | None:
    """Open a read connection, fetch one thread row, then close."""
    conn = connect(db_path)
    try:
        return conn.execute(
            f"SELECT {_THREAD_COLS} FROM threads WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    finally:
        conn.close()


def read_thread_events(
    db_path: Path, thread_id: str, since: int
) -> list[sqlite3.Row] | None:
    """Return a thread's turns with id > since (ascending), or None if no such thread.

    Existence is checked in the same connection so the route can 404 a missing thread
    without confusing it with a valid thread that has no new events (empty list).
    """
    conn = connect(db_path)
    try:
        if conn.execute(
            "SELECT 1 FROM threads WHERE thread_id = ?", (thread_id,)
        ).fetchone() is None:
            return None
        return conn.execute(
            f"SELECT {_EVENT_COLS} FROM turns WHERE thread_id = ? AND id > ? ORDER BY id",
            (thread_id, since),
        ).fetchall()
    finally:
        conn.close()
