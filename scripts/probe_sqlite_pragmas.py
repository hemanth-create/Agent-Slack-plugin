"""
probe_sqlite_pragmas.py
Verify that Python stdlib sqlite3 honors WAL + synchronous=FULL on this machine.
Exit 0 = pass, exit 1 = fail.
"""
import sqlite3
import tempfile
import os
import sys


def _open_with_pragmas(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _read_pragma(conn: sqlite3.Connection, name: str) -> str:
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def run() -> bool:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "probe.db")
        conn = _open_with_pragmas(db_path)

        journal = _read_pragma(conn, "journal_mode")
        sync = _read_pragma(conn, "synchronous")
        fk = _read_pragma(conn, "foreign_keys")
        user_ver = _read_pragma(conn, "user_version")

        conn.close()

        results = {
            "journal_mode": (journal, "wal"),
            "synchronous":  (sync,    "2"),        # 2 = FULL
            "foreign_keys": (fk,      "1"),
            "user_version": (user_ver, "0"),        # baseline
        }

        passed = True
        for pragma, (got, want) in results.items():
            ok = str(got).lower() == str(want).lower()
            status = "PASS" if ok else "FAIL"
            print(f"  {status}  {pragma}: got={got!r}  want={want!r}")
            if not ok:
                passed = False

        return passed


if __name__ == "__main__":
    print("=== P0-1: SQLite PRAGMA compliance ===")
    ok = run()
    print(f"\nResult: {'PASS — WAL+FULL honored' if ok else 'FAIL — pragmas not applied'}")
    sys.exit(0 if ok else 1)
