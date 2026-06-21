"""Tests for thread creation DB writes."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from router.db.init_db import init_db
from router.db.leases import acquire_lease
from router.db.threads import create_thread, set_thread_status
from router.errors import AcceptError
from router.paths import SCHEMA_PATH


def _db(tmp_path: Path) -> sqlite3.Connection:
    return init_db(tmp_path / "router.db", SCHEMA_PATH)


def test_create_thread_returns_active_state(tmp_path: Path) -> None:
    row = create_thread(_db(tmp_path), "t1", "ws", "claude")
    assert row["thread_id"] == "t1"
    assert row["status"] == "active"
    assert row["status_reason"] is None
    assert row["baton"] == "claude"
    assert row["last_turn_id"] == 0
    assert row["workspace_id"] == "ws"
    assert row["created_at"].endswith("+00:00")


def test_create_thread_uses_supplied_baton(tmp_path: Path) -> None:
    row = create_thread(_db(tmp_path), "t1", "ws", "codex")
    assert row["baton"] == "codex"


def test_create_thread_duplicate_is_structured(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    create_thread(conn, "t1", "ws", "claude")
    with pytest.raises(AcceptError) as exc:
        create_thread(conn, "t1", "ws", "claude")
    assert exc.value.code == "thread_exists"
    assert exc.value.http_status == 409
    assert conn.in_transaction is False


def test_set_done_clears_baton_and_marks_dirty(tmp_path: Path) -> None:
    conn = _thread_with_lease(tmp_path)
    row = set_thread_status(conn, "t1", "claude", "done", None)
    assert row["status"] == "done"
    assert row["status_reason"] is None
    assert row["baton"] is None
    assert _dirty_flag(conn) == 1


def test_set_needs_human_preserves_baton_and_marks_dirty(tmp_path: Path) -> None:
    conn = _thread_with_lease(tmp_path)
    row = set_thread_status(conn, "t1", "claude", "needs_human", "recovery_required")
    assert row["status"] == "needs_human"
    assert row["status_reason"] == "recovery_required"
    assert row["baton"] == "claude"
    assert _dirty_flag(conn) == 1


def test_set_cancelled_clears_baton_and_marks_dirty(tmp_path: Path) -> None:
    conn = _thread_with_lease(tmp_path)
    row = set_thread_status(conn, "t1", "claude", "cancelled", "user_cancelled")
    assert row["status"] == "cancelled"
    assert row["status_reason"] == "user_cancelled"
    assert row["baton"] is None
    assert _dirty_flag(conn) == 1


def test_set_status_rejects_incoherent_pairs(tmp_path: Path) -> None:
    conn = _thread_with_lease(tmp_path)
    _assert_status_error(conn, "active", None, "invalid_status")
    _assert_status_error(conn, "done", "user_cancelled", "invalid_status")
    _assert_status_error(conn, "blocked", None, "reason_required")
    _assert_status_error(conn, "blocked", "bad_reason", "invalid_status")


def test_set_status_rejects_non_active_thread(tmp_path: Path) -> None:
    conn = _thread_with_lease(tmp_path)
    set_thread_status(conn, "t1", "claude", "done", None)
    _assert_status_error(conn, "done", None, "not_active")


def test_set_status_rejects_wrong_baton(tmp_path: Path) -> None:
    conn = _thread_with_lease(tmp_path, baton="codex")
    _assert_status_error(conn, "done", None, "not_baton")


def test_set_status_requires_active_lease(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    create_thread(conn, "t1", "ws", "claude")
    _assert_status_error(conn, "done", None, "lease_required")


def _thread_with_lease(tmp_path: Path, baton: str = "claude") -> sqlite3.Connection:
    conn = _db(tmp_path)
    create_thread(conn, "t1", "ws", baton)
    acquire_lease(conn, "claude", "t1", 300)
    return conn


def _assert_status_error(
    conn: sqlite3.Connection, status: str, reason: str | None, code: str
) -> None:
    with pytest.raises(AcceptError) as exc:
        set_thread_status(conn, "t1", "claude", status, reason)
    assert exc.value.code == code
    assert conn.in_transaction is False


def _dirty_flag(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT dirty FROM projections_dirty WHERE thread_id='t1'").fetchone()
    return int(row["dirty"])
