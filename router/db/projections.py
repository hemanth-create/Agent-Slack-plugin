"""DB helpers for loading and clearing generated projection work."""
from __future__ import annotations

import sqlite3


def dirty_thread_ids(conn: sqlite3.Connection) -> list[str]:
    """Return thread ids whose projections need regeneration."""
    rows = conn.execute(
        "SELECT thread_id FROM projections_dirty WHERE dirty=1 ORDER BY thread_id"
    ).fetchall()
    return [str(row["thread_id"]) for row in rows]


def load_projection(conn: sqlite3.Connection, thread_id: str) -> dict | None:
    """Load thread state, turns, and participants for projection rendering."""
    thread = conn.execute(
        "SELECT thread_id, status, status_reason, baton, last_turn_id, workspace_id, created_at "
        "FROM threads WHERE thread_id=?",
        (thread_id,),
    ).fetchone()
    if thread is None:
        return None
    return {
        "thread": dict(thread),
        "turns": _turns(conn, thread_id),
        "participants": _participants(conn, thread_id),
    }


def load_projection_snapshot(conn: sqlite3.Connection, thread_id: str) -> dict | None:
    """Load one projection from a consistent read transaction."""
    conn.execute("BEGIN")
    try:
        data = load_projection(conn, thread_id)
        conn.execute("COMMIT")
        return data
    except Exception:
        _rollback(conn)
        raise


def _rollback(conn: sqlite3.Connection) -> None:
    """Best-effort rollback that preserves the original exception."""
    try:
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError:
        pass


def _turns(conn: sqlite3.Connection, thread_id: str) -> list[dict]:
    """Return public turn projection rows in ascending id order."""
    rows = conn.execute(
        "SELECT id, author, reply_to, ts, body FROM turns WHERE thread_id=? ORDER BY id",
        (thread_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _participants(conn: sqlite3.Connection, thread_id: str) -> list[dict]:
    """Return participant cursor projection rows sorted by agent."""
    rows = conn.execute(
        "SELECT agent, last_processed_id FROM participants WHERE thread_id=? ORDER BY agent",
        (thread_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_rendered(conn: sqlite3.Connection, thread_id: str, last_turn_id: int) -> bool:
    """Clear dirty only if the rendered head is still current."""
    cur = conn.execute(
        "UPDATE projections_dirty SET dirty=0, last_rendered_turn_id=? "
        "WHERE thread_id=? AND ?=(SELECT last_turn_id FROM threads WHERE thread_id=?)",
        (last_turn_id, thread_id, last_turn_id, thread_id),
    )
    return cur.rowcount == 1
