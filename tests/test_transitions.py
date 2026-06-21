"""Tests for the atomic halt/resume transitions (append + status flip in one txn)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from router.db.accept import TurnRequest
from router.db.init_db import init_db
from router.db.transitions import accept_halt_turn, accept_resume_turn
from router.errors import AcceptError
from router.paths import SCHEMA_PATH

_FUTURE = "9999-12-31T23:59:59+00:00"


def _seed(
    conn: sqlite3.Connection, *, baton: str | None = "claude", status: str = "active",
    reason: str | None = None, last: int = 0, lease: bool = True,
) -> None:
    conn.execute(
        "INSERT INTO threads(thread_id, status, status_reason, baton, last_turn_id, "
        "workspace_id, created_at) VALUES('t1',?,?,?,?,'ws','now')",
        (status, reason, baton, last),
    )
    if lease:
        conn.execute(
            "INSERT INTO leases(lease_id, thread_id, agent, acquired_at, expires_at, status) "
            "VALUES('L1','t1','claude','now',?,'active')",
            (_FUTURE,),
        )


def _db(tmp_path: Path, **seed: object) -> sqlite3.Connection:
    conn = init_db(tmp_path / "router.db", SCHEMA_PATH)
    _seed(conn, **seed)
    return conn


def _req(**over: object) -> TurnRequest:
    base = dict(
        thread_id="t1", body="answer", reply_to=None, next_baton="claude",
        idempotency_key="k1", expected_last_turn_id=0, processed_through_id=0,
    )
    base.update(over)
    return TurnRequest(**base)  # type: ignore[arg-type]


def _thread(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute(
        "SELECT status, status_reason, baton, last_turn_id FROM threads WHERE thread_id='t1'"
    ).fetchone()


# ---- halt -----------------------------------------------------------------

def test_halt_needs_human_keeps_baton_and_advances_head(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    turn = accept_halt_turn(conn, "claude", _req(), "needs_human", "recovery_required")
    t = _thread(conn)
    assert t["status"] == "needs_human" and t["status_reason"] == "recovery_required"
    assert t["baton"] == "claude"               # halter keeps the baton
    assert t["last_turn_id"] == turn["id"]       # head advanced to the halt turn
    assert conn.execute("SELECT COUNT(*) c FROM turns").fetchone()["c"] == 1


def test_halt_done_clears_baton_and_forbids_reason(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    accept_halt_turn(conn, "claude", _req(), "done", None)
    t = _thread(conn)
    assert t["status"] == "done" and t["status_reason"] is None and t["baton"] is None


def test_halt_replays_same_key(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    first = accept_halt_turn(conn, "claude", _req(), "needs_human", "recovery_required")
    second = accept_halt_turn(conn, "claude", _req(), "needs_human", "recovery_required")
    assert second["id"] == first["id"]
    assert conn.execute("SELECT COUNT(*) c FROM turns").fetchone()["c"] == 1


def test_halt_requires_baton(tmp_path: Path) -> None:
    conn = _db(tmp_path, baton="codex")
    with pytest.raises(AcceptError) as exc:
        accept_halt_turn(conn, "claude", _req(), "needs_human", "recovery_required")
    assert exc.value.code == "not_baton"


def test_halt_requires_lease(tmp_path: Path) -> None:
    conn = _db(tmp_path, lease=False)
    with pytest.raises(AcceptError) as exc:
        accept_halt_turn(conn, "claude", _req(), "blocked", "recovery_required")
    assert exc.value.code == "lease_required"


def test_halt_rejects_bad_status(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    with pytest.raises(AcceptError) as exc:
        accept_halt_turn(conn, "claude", _req(), "continue", None)
    assert exc.value.code == "invalid_status"


def test_halt_rolls_back_on_gate_failure(tmp_path: Path) -> None:
    conn = _db(tmp_path, baton="codex")
    with pytest.raises(AcceptError):
        accept_halt_turn(conn, "claude", _req(), "needs_human", "recovery_required")
    assert conn.in_transaction is False
    assert conn.execute("SELECT COUNT(*) c FROM turns").fetchone()["c"] == 0


# ---- resume ---------------------------------------------------------------

def test_resume_reactivates_halted_thread(tmp_path: Path) -> None:
    conn = _db(tmp_path, status="needs_human", reason="recovery_required", baton="claude")
    turn = accept_resume_turn(conn, "codex", _req(body="here is the answer", next_baton="claude"))
    t = _thread(conn)
    assert t["status"] == "active" and t["status_reason"] is None
    assert t["baton"] == "claude" and t["last_turn_id"] == turn["id"]
    assert turn["author"] == "codex" and turn["body"] == "here is the answer"


def test_resume_on_active_thread_is_not_resumable(tmp_path: Path) -> None:
    conn = _db(tmp_path)  # active
    with pytest.raises(AcceptError) as exc:
        accept_resume_turn(conn, "codex", _req())
    assert exc.value.code == "not_resumable"
    assert conn.execute("SELECT COUNT(*) c FROM turns").fetchone()["c"] == 0  # rolled back


def test_resume_stale_expected_is_not_resumable(tmp_path: Path) -> None:
    conn = _db(tmp_path, status="blocked", reason="recovery_required", last=2)
    with pytest.raises(AcceptError) as exc:
        accept_resume_turn(conn, "codex", _req(expected_last_turn_id=0))
    assert exc.value.code == "not_resumable"


def test_resume_replays_same_key(tmp_path: Path) -> None:
    conn = _db(tmp_path, status="needs_human", reason="recovery_required", baton="claude")
    first = accept_resume_turn(conn, "codex", _req(next_baton="claude"))
    second = accept_resume_turn(conn, "codex", _req(next_baton="claude"))  # already active
    assert second["id"] == first["id"]
    assert conn.execute("SELECT COUNT(*) c FROM turns").fetchone()["c"] == 1
