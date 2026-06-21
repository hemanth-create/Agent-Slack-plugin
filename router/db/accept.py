"""The single-writer accept transaction: one BEGIN IMMEDIATE, fixed 13-step order."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from router.db import gates, writes
from router.hashing import payload_hash


@dataclass
class TurnRequest:
    """Validated submission fields handed to the transaction (auth_agent is separate)."""

    thread_id: str
    body: str
    reply_to: int | None
    next_baton: str
    idempotency_key: str
    expected_last_turn_id: int
    processed_through_id: int


@dataclass
class AcceptOutcome:
    """The accepted (or replayed) turn plus whether it was newly created."""

    turn: dict
    created: bool


def _hash(req: TurnRequest) -> str:
    """Canonical idempotency hash over the semantic submission fields."""
    return payload_hash(
        {
            "thread_id": req.thread_id,
            "body": req.body,
            "reply_to": req.reply_to,
            "next_baton": req.next_baton,
            "expected_last_turn_id": req.expected_last_turn_id,
            "processed_through_id": req.processed_through_id,
        }
    )


def _apply(conn: sqlite3.Connection, agent: str, req: TurnRequest, phash: str, now: str) -> int:
    """Run the gate checks then the write steps; return the new turn id."""
    thread = gates.load_active_thread(conn, req.thread_id)
    gates.check_baton(thread, agent)
    gates.check_lease(conn, req.thread_id, agent, now)
    gates.check_cas(thread, req.expected_last_turn_id)
    gates.check_read_coverage(thread, req.processed_through_id)
    turn_id = writes.append_turn(
        conn, req.thread_id, agent, req.reply_to, now, req.body, phash
    )
    writes.advance_cursor(conn, req.thread_id, agent, turn_id)
    writes.flip_baton(conn, req.thread_id, req.next_baton, turn_id, req.expected_last_turn_id)
    writes.store_idempotency(conn, req.thread_id, agent, req.idempotency_key, phash, turn_id, now)
    writes.mark_dirty(conn, req.thread_id)
    return turn_id


def _rollback(conn: sqlite3.Connection) -> None:
    """Best-effort rollback that preserves the original exception."""
    try:
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError:
        pass


def accept_turn(conn: sqlite3.Connection, agent: str, req: TurnRequest) -> AcceptOutcome:
    """Accept a turn under one BEGIN IMMEDIATE; raise AcceptError on a gate failure."""
    phash = _hash(req)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("BEGIN IMMEDIATE")
    try:
        stored = gates.lookup_idempotency(conn, req.thread_id, agent, req.idempotency_key, phash)
        if stored is not None:
            turn = writes.fetch_turn(conn, stored)
            conn.execute("ROLLBACK")
            return AcceptOutcome(turn, created=False)
        turn_id = _apply(conn, agent, req, phash, now)
        turn = writes.fetch_turn(conn, turn_id)
        conn.execute("COMMIT")
        return AcceptOutcome(turn, created=True)
    except Exception:
        _rollback(conn)
        raise
