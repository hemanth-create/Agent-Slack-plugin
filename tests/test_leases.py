"""Tests for lease lifecycle DB operations."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from router.db.init_db import init_db
from router.db.leases import acquire_lease, release_lease, renew_lease
from router.errors import AcceptError
from router.paths import SCHEMA_PATH


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "router.db", SCHEMA_PATH)
    conn.execute(
        "INSERT INTO threads(thread_id, status, baton, workspace_id, created_at) "
        "VALUES('t1','active','claude','ws','now')"
    )
    return conn


def test_acquire_creates_active_lease(tmp_path: Path) -> None:
    row = acquire_lease(_db(tmp_path), "claude", "t1", 300)
    assert row["agent"] == "claude"
    assert row["status"] == "active"


def test_acquire_extends_same_agents_lease(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    first = acquire_lease(conn, "claude", "t1", 300)
    second = acquire_lease(conn, "claude", "t1", 600)
    count = conn.execute("SELECT COUNT(*) c FROM leases").fetchone()["c"]
    assert second["lease_id"] == first["lease_id"]
    assert count == 1


def test_acquire_rejects_other_active_agent(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    acquire_lease(conn, "claude", "t1", 300)
    with pytest.raises(AcceptError) as exc:
        acquire_lease(conn, "codex", "t1", 300)
    assert exc.value.code == "lease_conflict"
    assert conn.in_transaction is False
    count = conn.execute("SELECT COUNT(*) c FROM leases").fetchone()["c"]
    assert count == 1


def test_acquire_after_expired_lease_keeps_thread_active(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    conn.execute(
        "INSERT INTO leases(lease_id, thread_id, agent, acquired_at, expires_at, status) "
        "VALUES('old','t1','codex','now','2000-01-01T00:00:00+00:00','active')"
    )
    row = acquire_lease(conn, "claude", "t1", 300)
    thread = conn.execute("SELECT status FROM threads WHERE thread_id='t1'").fetchone()
    assert row["agent"] == "claude"
    assert thread["status"] == "active"


def test_acquire_does_not_sweep_other_threads(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    conn.executescript(
        "INSERT INTO threads(thread_id, status, baton, workspace_id, created_at) "
        "VALUES('t2','active','codex','ws','now');"
        "INSERT INTO leases(lease_id, thread_id, agent, acquired_at, expires_at, status) "
        "VALUES('old','t2','codex','now','2000-01-01T00:00:00+00:00','active');"
    )
    acquire_lease(conn, "claude", "t1", 300)
    thread = conn.execute("SELECT status FROM threads WHERE thread_id='t2'").fetchone()
    lease = conn.execute("SELECT status FROM leases WHERE lease_id='old'").fetchone()
    assert thread["status"] == "active"
    assert lease["status"] == "active"


def test_renew_extends_owned_active_lease(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    lease = acquire_lease(conn, "claude", "t1", 300)
    renewed = renew_lease(conn, "claude", "t1", lease["lease_id"], 600)
    assert renewed["lease_id"] == lease["lease_id"]
    assert renewed["heartbeat_at"] is not None


def test_renew_failure_closes_transaction(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    with pytest.raises(AcceptError):
        renew_lease(conn, "claude", "t1", "missing", 300)
    assert conn.in_transaction is False


def test_release_marks_owned_lease_released(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    lease = acquire_lease(conn, "claude", "t1", 300)
    released = release_lease(conn, "claude", "t1", lease["lease_id"])
    assert released["status"] == "released"


def test_release_failure_closes_transaction(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    with pytest.raises(AcceptError):
        release_lease(conn, "claude", "t1", "missing")
    assert conn.in_transaction is False
