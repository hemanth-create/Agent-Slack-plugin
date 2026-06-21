"""SQLite connection factory: applies the required PRAGMAs on every open."""
from __future__ import annotations

import sqlite3
from pathlib import Path

_BUSY_TIMEOUT_MS = 5000


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Set the durability/concurrency PRAGMAs required on every connection."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")


def connect(db_path: Path, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a SQLite connection in autocommit mode with router PRAGMAs applied.

    The single writer connection passes check_same_thread=False because it is created
    in the app lifespan but used from asyncio.to_thread worker threads under the writer
    lock (only one accept runs at a time, so the connection is never used concurrently).
    """
    conn = sqlite3.connect(
        db_path, isolation_level=None, check_same_thread=check_same_thread
    )
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    return conn


def quick_check(conn: sqlite3.Connection) -> str:
    """Return PRAGMA quick_check ('ok' when the DB is intact).

    This is a full-database integrity scan, run once at startup via
    startup_checks.assert_db_intact -- deliberately NOT part of connect(),
    because scanning the whole DB on every connection open is too expensive.
    The per-open invariants are the four session PRAGMAs in _apply_pragmas.
    """
    row = conn.execute("PRAGMA quick_check").fetchone()
    return "missing" if row is None else str(row[0])
