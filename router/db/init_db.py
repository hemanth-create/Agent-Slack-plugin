"""Initialize router.db: apply the schema on first run, enforce schema version."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from router.db.connection import connect

# Bump when schema.sql changes; add a migration step in init_db for each increment.
SCHEMA_VERSION = 1


def _current_version(conn: sqlite3.Connection) -> int:
    """Return the DB's PRAGMA user_version (0 for a brand-new database)."""
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def _apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    """Run the schema DDL and stamp the current schema version."""
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def _check_version(version: int) -> None:
    """Refuse to run against a newer (unknown) schema version."""
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"router.db schema version {version} is newer than supported "
            f"{SCHEMA_VERSION}; upgrade the router or restore a compatible DB."
        )


def assert_schema_current(conn: sqlite3.Connection) -> None:
    """Raise unless the DB's user_version equals the supported SCHEMA_VERSION."""
    version = _current_version(conn)
    if version != SCHEMA_VERSION:
        raise RuntimeError(
            f"router.db schema version {version} != supported {SCHEMA_VERSION}; "
            "re-run scripts.init_db or restore a compatible DB."
        )


def init_db(db_path: Path, schema_path: Path) -> sqlite3.Connection:
    """Open (creating if needed) and return a ready router.db connection."""
    conn = connect(db_path)
    version = _current_version(conn)
    if version == 0:
        _apply_schema(conn, schema_path)
    else:
        _check_version(version)
    return conn
