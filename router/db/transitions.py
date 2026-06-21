"""Atomic halt and resume transitions: append a turn AND change status in one txn.

Both run under a single BEGIN IMMEDIATE so the head advance and the status change
commit together -- closing the `active AND baton=self` crash window a two-call
(submit then status) design would leave. Idempotent on the submitter's key.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from router.db import gates, threads, writes
from router.db.accept import TurnRequest, _hash  # reuse the canonical idempotency hash


def _rollback(conn: sqlite3.Connection) -> None:
    """Best-effort rollback that preserves the original exception."""
    try:
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError:
        pass


def accept_halt_turn(
    conn: sqlite3.Connection, agent: str, req: TurnRequest, status: str, reason: str | None
) -> dict:
    """Record the halting turn and flip status, under one BEGIN IMMEDIATE. Idempotent."""
    status, reason = threads.validate_status_update(status, reason)
    phash = _hash(req)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("BEGIN IMMEDIATE")
    try:
        stored = gates.lookup_idempotency(conn, req.thread_id, agent, req.idempotency_key, phash)
        if stored is not None:
            turn = writes.fetch_turn(conn, stored)
            conn.execute("ROLLBACK")
            return turn
        turn_id = _apply_halt(conn, agent, req, phash, now, status, reason)
        turn = writes.fetch_turn(conn, turn_id)
        conn.execute("COMMIT")
        return turn
    except Exception:
        _rollback(conn)
        raise


def _apply_halt(
    conn: sqlite3.Connection, agent: str, req: TurnRequest, phash: str, now: str,
    status: str, reason: str | None,
) -> int:
    """Same gates as accept_turn, but flip_to_halt replaces flip_baton."""
    thread = gates.load_active_thread(conn, req.thread_id)
    gates.check_baton(thread, agent)
    gates.check_lease(conn, req.thread_id, agent, now)
    gates.check_cas(thread, req.expected_last_turn_id)
    gates.check_read_coverage(thread, req.processed_through_id)
    turn_id = writes.append_turn(conn, req.thread_id, agent, req.reply_to, now, req.body, phash)
    writes.advance_cursor(conn, req.thread_id, agent, turn_id)
    baton = None if status in threads._CLEAR_BATON_STATUSES else agent  # keep self for needs_human/blocked
    writes.flip_to_halt(conn, req.thread_id, status, reason, baton, turn_id, req.expected_last_turn_id)
    writes.store_idempotency(conn, req.thread_id, agent, req.idempotency_key, phash, turn_id, now)
    writes.mark_dirty(conn, req.thread_id)
    return turn_id


def accept_resume_turn(conn: sqlite3.Connection, operator: str, req: TurnRequest) -> dict:
    """Append the operator's answer AND reactivate a halted thread; head advances -> wake fires."""
    phash = _hash(req)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("BEGIN IMMEDIATE")
    try:
        stored = gates.lookup_idempotency(conn, req.thread_id, operator, req.idempotency_key, phash)
        if stored is not None:
            turn = writes.fetch_turn(conn, stored)
            conn.execute("ROLLBACK")
            return turn
        turn_id = writes.append_turn(conn, req.thread_id, operator, req.reply_to, now, req.body, phash)
        writes.reactivate_head(conn, req.thread_id, req.next_baton, turn_id, req.expected_last_turn_id)
        writes.store_idempotency(conn, req.thread_id, operator, req.idempotency_key, phash, turn_id, now)
        writes.mark_dirty(conn, req.thread_id)
        turn = writes.fetch_turn(conn, turn_id)
        conn.execute("COMMIT")
        return turn
    except Exception:
        _rollback(conn)
        raise
