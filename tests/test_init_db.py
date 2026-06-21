"""Tests for router.db.init_db: schema creation, versioning, constraints."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from router.db.init_db import SCHEMA_VERSION, assert_schema_current, init_db
from router.paths import SCHEMA_PATH

_TABLES = {"threads", "turns", "leases", "participants", "idempotency", "projections_dirty"}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def _fresh_db(tmp_path: Path) -> sqlite3.Connection:
    return init_db(tmp_path / "router.db", SCHEMA_PATH)


def test_creates_all_tables(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    assert _TABLES <= _table_names(conn)


def test_stamps_schema_version(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_reinit_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "router.db"
    init_db(db, SCHEMA_PATH).close()
    conn = init_db(db, SCHEMA_PATH)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_refuses_newer_version(tmp_path: Path) -> None:
    db = tmp_path / "router.db"
    conn = init_db(db, SCHEMA_PATH)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(RuntimeError, match="newer than supported"):
        init_db(db, SCHEMA_PATH)


def test_assert_schema_current_rejects_mismatch(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "router.db", SCHEMA_PATH)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError, match="!= supported"):
        assert_schema_current(conn)


def test_idempotency_key_is_unique(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    conn.execute(
        "INSERT INTO threads(thread_id, workspace_id, created_at) VALUES('t1','ws','now')"
    )
    conn.execute(
        "INSERT INTO turns(thread_id, author, ts, body, payload_hash) "
        "VALUES('t1','claude','now','hi','h')"
    )
    insert = (
        "INSERT INTO idempotency(thread_id, auth_agent, idempotency_key, payload_hash, "
        "stored_turn_id, created_at) VALUES('t1','claude','k1','h',1,'now')"
    )
    conn.execute(insert)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert)


def test_needs_human_requires_reason(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO threads(thread_id, status, workspace_id, created_at) "
            "VALUES('t1','needs_human','ws','now')"
        )


def test_active_rejects_status_reason(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO threads(thread_id, status, status_reason, workspace_id, "
            "created_at) VALUES('t1','active','disconnected','ws','now')"
        )


def _two_threads_one_turn(conn: sqlite3.Connection) -> None:
    """Seed threads 'a' and 'b' plus a single turn (id=1) belonging to 'a'."""
    conn.executescript(
        "INSERT INTO threads(thread_id, workspace_id, created_at) VALUES('a','ws','now');"
        "INSERT INTO threads(thread_id, workspace_id, created_at) VALUES('b','ws','now');"
        "INSERT INTO turns(thread_id, author, ts, body, payload_hash) "
        "VALUES('a','claude','now','hi','h');"
    )


def test_reply_to_must_be_same_thread(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    _two_threads_one_turn(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO turns(thread_id, author, reply_to, ts, body, payload_hash) "
            "VALUES('b','codex',1,'now','re','h')"
        )


def test_idempotency_turn_must_be_same_thread(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    _two_threads_one_turn(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO idempotency(thread_id, auth_agent, idempotency_key, "
            "payload_hash, stored_turn_id, created_at) VALUES('b','codex','k1','h',1,'now')"
        )
