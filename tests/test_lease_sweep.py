"""Tests for the dedicated lease expiry sweep."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from router.db.init_db import init_db
from router.db.lease_sweep import sweep_expired_leases
from router.paths import SCHEMA_PATH


class _FailingThreadUpdate:
    """Connection proxy that fails after leases are marked expired."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        if sql.startswith("UPDATE threads SET status='needs_human'"):
            raise sqlite3.OperationalError("forced thread update failure")
        return self.conn.execute(sql, params)


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "router.db", SCHEMA_PATH)
    conn.execute(
        "INSERT INTO threads(thread_id, status, baton, workspace_id, created_at) "
        "VALUES('t1','active','claude','ws','now')"
    )
    return conn


def _expired_lease(conn: sqlite3.Connection, lease_id: str, thread_id: str = "t1") -> None:
    conn.execute(
        "INSERT INTO leases(lease_id, thread_id, agent, acquired_at, expires_at, status) "
        "VALUES(?,?, 'claude','now','2000-01-01T00:00:00+00:00','active')",
        (lease_id, thread_id),
    )


def test_sweep_marks_thread_needs_human_and_preserves_baton(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _expired_lease(conn, "old")
    result = sweep_expired_leases(conn, "2026-01-01T00:00:00+00:00")
    thread = conn.execute("SELECT status, status_reason, baton FROM threads").fetchone()
    lease = conn.execute("SELECT status FROM leases WHERE lease_id='old'").fetchone()
    assert result == {"expired_leases": 1, "threads_disconnected": 1}
    assert dict(thread) == {
        "status": "needs_human",
        "status_reason": "disconnected",
        "baton": "claude",
    }
    assert lease["status"] == "expired"


def test_sweep_keeps_thread_active_when_another_lease_is_valid(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _expired_lease(conn, "old")
    conn.execute(
        "INSERT INTO leases(lease_id, thread_id, agent, acquired_at, expires_at, status) "
        "VALUES('new','t1','claude','now','9999-01-01T00:00:00+00:00','active')"
    )
    result = sweep_expired_leases(conn, "2026-01-01T00:00:00+00:00")
    thread = conn.execute("SELECT status, status_reason FROM threads").fetchone()
    assert result == {"expired_leases": 1, "threads_disconnected": 0}
    assert thread["status"] == "active"
    assert thread["status_reason"] is None


def test_sweep_rolls_back_if_thread_flip_fails(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _expired_lease(conn, "old")
    with pytest.raises(sqlite3.OperationalError):
        sweep_expired_leases(_FailingThreadUpdate(conn), "2026-01-01T00:00:00+00:00")
    lease = conn.execute("SELECT status FROM leases WHERE lease_id='old'").fetchone()
    thread = conn.execute("SELECT status FROM threads").fetchone()
    assert conn.in_transaction is False
    assert lease["status"] == "active"
    assert thread["status"] == "active"
