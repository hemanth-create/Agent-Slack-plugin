"""Read-only accept-transaction gates; each raises AcceptError on failure."""
from __future__ import annotations

import sqlite3

from router.errors import AcceptError


def lookup_idempotency(
    conn: sqlite3.Connection, thread_id: str, agent: str, key: str, phash: str
) -> int | None:
    """Return the stored turn id for a matching key, None if the key is new.

    Raises idempotency_conflict (409) if the key exists with a different payload.
    """
    row = conn.execute(
        "SELECT payload_hash, stored_turn_id FROM idempotency "
        "WHERE thread_id=? AND auth_agent=? AND idempotency_key=?",
        (thread_id, agent, key),
    ).fetchone()
    if row is None:
        return None
    if row["payload_hash"] != phash:
        raise AcceptError("idempotency_conflict", 409)
    return int(row["stored_turn_id"])


def load_active_thread(conn: sqlite3.Connection, thread_id: str) -> sqlite3.Row:
    """Return the thread row; 404 if missing, 409 (status_reason) if not active."""
    row = conn.execute(
        "SELECT status, status_reason, baton, last_turn_id FROM threads WHERE thread_id=?",
        (thread_id,),
    ).fetchone()
    if row is None:
        raise AcceptError("thread_not_found", 404)
    if row["status"] != "active":
        raise AcceptError(row["status_reason"] or "not_active", 409)
    return row


def check_baton(thread: sqlite3.Row, agent: str) -> None:
    """Raise not_baton (409) unless agent currently holds the baton."""
    if thread["baton"] != agent:
        raise AcceptError("not_baton", 409)


def check_lease(conn: sqlite3.Connection, thread_id: str, agent: str, now: str) -> None:
    """Raise lease_required (409) unless agent holds an active, unexpired lease."""
    row = conn.execute(
        "SELECT 1 FROM leases WHERE thread_id=? AND agent=? AND status='active' "
        "AND expires_at > ?",
        (thread_id, agent, now),
    ).fetchone()
    if row is None:
        raise AcceptError("lease_required", 409)


def check_cas(thread: sqlite3.Row, expected_last_turn_id: int) -> None:
    """Raise stale_base (409) if the CAS base does not match the thread head."""
    if thread["last_turn_id"] != expected_last_turn_id:
        raise AcceptError("stale_base", 409)


def check_read_coverage(thread: sqlite3.Row, processed_through_id: int) -> None:
    """Raise stale_read (409) if the submitter has not processed through the head."""
    if processed_through_id < thread["last_turn_id"]:
        raise AcceptError("stale_read", 409)
