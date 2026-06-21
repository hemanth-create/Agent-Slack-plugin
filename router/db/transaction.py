"""Small SQLite transaction helpers for DB-layer write operations."""
from __future__ import annotations

from collections.abc import Callable
import sqlite3
from typing import TypeVar

T = TypeVar("T")


def rollback(conn: sqlite3.Connection) -> None:
    """Best-effort rollback that preserves the original exception."""
    try:
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError:
        pass


def run_immediate(conn: sqlite3.Connection, work: Callable[[], T]) -> T:
    """Run work inside one BEGIN IMMEDIATE transaction."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        result = work()
        conn.execute("COMMIT")
        return result
    except Exception:
        rollback(conn)
        raise
