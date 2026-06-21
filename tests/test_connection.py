"""Tests for router.db.connection: PRAGMA application and FK enforcement."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from router.db.connection import connect
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH


def _pragma(conn: sqlite3.Connection, name: str) -> object:
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def test_pragmas_are_applied(tmp_path: Path) -> None:
    conn = connect(tmp_path / "router.db")
    assert str(_pragma(conn, "journal_mode")).lower() == "wal"
    assert _pragma(conn, "synchronous") == 2  # 2 == FULL
    assert _pragma(conn, "foreign_keys") == 1
    assert _pragma(conn, "busy_timeout") == 5000


def test_foreign_keys_enforced(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "router.db", SCHEMA_PATH)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO turns(thread_id, author, ts, body, payload_hash) "
            "VALUES('missing','claude','now','hi','h')"
        )
