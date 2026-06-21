"""Dev helper: seed one active thread for local manual testing.

Temporary until a `POST /threads` endpoint exists. Run from the repo root:
    python -m scripts.seed_thread [thread_id] [baton]
"""
from __future__ import annotations

import sys

from router.db.connection import connect
from router.paths import DB_PATH


def seed_thread(thread_id: str, baton: str = "claude") -> None:
    """Insert one active thread (idempotent) so the lease/turn APIs have a target."""
    conn = connect(DB_PATH)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO threads(thread_id, status, baton, workspace_id, created_at) "
            "VALUES(?, 'active', ?, 'local', 'now')",
            (thread_id, baton),
        )
    finally:
        conn.close()
    print(f"seeded thread {thread_id!r} (baton={baton})")


def main() -> int:
    """CLI entrypoint: optional [thread_id] [baton], defaulting to demo/claude."""
    thread_id = sys.argv[1] if len(sys.argv) > 1 else "demo"
    baton = sys.argv[2] if len(sys.argv) > 2 else "claude"
    seed_thread(thread_id, baton)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
