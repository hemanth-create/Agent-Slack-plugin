"""Write statements for the accept transaction (called only inside accept_turn)."""
from __future__ import annotations

import sqlite3

from router.errors import AcceptError

_EVENT_COLS = "id, thread_id, author, reply_to, ts, body"


def append_turn(
    conn: sqlite3.Connection, thread_id: str, author: str, reply_to: int | None,
    ts: str, body: str, phash: str,
) -> int:
    """Insert the turn (server-assigned id); 409 invalid_reply_to on the FK violation."""
    try:
        cur = conn.execute(
            "INSERT INTO turns(thread_id, author, reply_to, ts, body, payload_hash) "
            "VALUES(?,?,?,?,?,?)",
            (thread_id, author, reply_to, ts, body, phash),
        )
    except sqlite3.IntegrityError as exc:  # reply_to is the only client-controlled FK
        raise AcceptError("invalid_reply_to", 409) from exc
    return int(cur.lastrowid)


def advance_cursor(conn: sqlite3.Connection, thread_id: str, agent: str, turn_id: int) -> None:
    """Move the author's read cursor up to the turn it just wrote."""
    conn.execute(
        "INSERT INTO participants(thread_id, agent, last_processed_id) VALUES(?,?,?) "
        "ON CONFLICT(thread_id, agent) DO UPDATE SET last_processed_id=excluded.last_processed_id",
        (thread_id, agent, turn_id),
    )


def flip_baton(
    conn: sqlite3.Connection, thread_id: str, next_baton: str,
    turn_id: int, expected_last_turn_id: int,
) -> None:
    """Advance the head from the CAS base to this turn and hand off the baton.

    The WHERE clause makes the compare-and-set the durable invariant: if the head
    moved off the expected base, no row matches and stale_base (409) is raised --
    so the head only ever advances from the base the submitter saw.
    """
    cur = conn.execute(
        "UPDATE threads SET baton=?, last_turn_id=? WHERE thread_id=? AND last_turn_id=?",
        (next_baton, turn_id, thread_id, expected_last_turn_id),
    )
    if cur.rowcount != 1:
        raise AcceptError("stale_base", 409)


def flip_to_halt(
    conn: sqlite3.Connection, thread_id: str, status: str, reason: str | None,
    baton: str | None, turn_id: int, expected_last_turn_id: int,
) -> None:
    """Advance the head AND flip an active thread to a halt status in one CAS UPDATE.

    Same compare-and-set base as flip_baton, so the status change is atomic with the
    head advance -- there is no `active AND baton=self` gap a crash could strand in.
    """
    cur = conn.execute(
        "UPDATE threads SET status=?, status_reason=?, baton=?, last_turn_id=? "
        "WHERE thread_id=? AND status='active' AND last_turn_id=?",
        (status, reason, baton, turn_id, thread_id, expected_last_turn_id),
    )
    if cur.rowcount != 1:
        raise AcceptError("stale_base", 409)


def reactivate_head(
    conn: sqlite3.Connection, thread_id: str, baton: str,
    turn_id: int, expected_last_turn_id: int,
) -> None:
    """Append-driven resume: move a halted thread back to active with the head advanced."""
    cur = conn.execute(
        "UPDATE threads SET status='active', status_reason=NULL, baton=?, last_turn_id=? "
        "WHERE thread_id=? AND status IN ('needs_human','blocked') AND last_turn_id=?",
        (baton, turn_id, thread_id, expected_last_turn_id),
    )
    if cur.rowcount != 1:
        raise AcceptError("not_resumable", 409)


def store_idempotency(
    conn: sqlite3.Connection, thread_id: str, agent: str, key: str, phash: str,
    turn_id: int, now: str,
) -> None:
    """Record the idempotency row pointing at the stored turn."""
    conn.execute(
        "INSERT INTO idempotency(thread_id, auth_agent, idempotency_key, payload_hash, "
        "stored_turn_id, created_at) VALUES(?,?,?,?,?,?)",
        (thread_id, agent, key, phash, turn_id, now),
    )


def mark_dirty(conn: sqlite3.Connection, thread_id: str) -> None:
    """Flag the thread's projections for regeneration (rendered in P2e)."""
    conn.execute(
        "INSERT INTO projections_dirty(thread_id, dirty, last_rendered_turn_id) "
        "VALUES(?,1,0) ON CONFLICT(thread_id) DO UPDATE SET dirty=1",
        (thread_id,),
    )


def fetch_turn(conn: sqlite3.Connection, turn_id: int) -> dict:
    """Return the stored turn row as a dict for the response model."""
    row = conn.execute(f"SELECT {_EVENT_COLS} FROM turns WHERE id=?", (turn_id,)).fetchone()
    return dict(row)
