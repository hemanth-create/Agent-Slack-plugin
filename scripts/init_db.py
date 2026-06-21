"""Create data/ and initialize router.db with the v0 schema (run once)."""
from __future__ import annotations

from router.config.startup_checks import assert_db_intact, assert_not_synced
from router.db.init_db import init_db
from router.paths import DB_PATH, SCHEMA_PATH, ensure_data_dir


def main() -> None:
    """Bootstrap the local database, refusing unsafe (synced) locations."""
    ensure_data_dir()
    assert_not_synced(DB_PATH)
    conn = init_db(DB_PATH, SCHEMA_PATH)
    assert_db_intact(conn)
    conn.close()
    print(f"Initialized {DB_PATH} (schema v1, integrity ok).")


if __name__ == "__main__":
    main()
