"""Tests for the accept transaction: idempotency replay/conflict and every gate."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from router.db import writes
from router.db.accept import TurnRequest, accept_turn
from router.db.init_db import init_db
from router.errors import AcceptError
from router.paths import SCHEMA_PATH

_FUTURE = "9999-12-31T23:59:59+00:00"


def _seed(
    conn: sqlite3.Connection, *, baton: str = "claude", status: str = "active",
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
        thread_id="t1", body="hi", reply_to=None, next_baton="codex",
        idempotency_key="k1", expected_last_turn_id=0, processed_through_id=0,
    )
    base.update(over)
    return TurnRequest(**base)  # type: ignore[arg-type]


def test_accept_creates_turn(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    out = accept_turn(conn, "claude", _req())
    assert out.created is True
    assert out.turn["author"] == "claude" and out.turn["body"] == "hi"
    row = conn.execute("SELECT baton, last_turn_id FROM threads WHERE thread_id='t1'").fetchone()
    assert row["baton"] == "codex" and row["last_turn_id"] == out.turn["id"]


def test_accept_replays_same_key(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    first = accept_turn(conn, "claude", _req())
    second = accept_turn(conn, "claude", _req())  # baton already moved to codex
    assert second.created is False and second.turn["id"] == first.turn["id"]
    assert conn.execute("SELECT COUNT(*) c FROM turns").fetchone()["c"] == 1


def test_accept_conflict_on_changed_payload(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    accept_turn(conn, "claude", _req(body="hi"))
    with pytest.raises(AcceptError) as exc:
        accept_turn(conn, "claude", _req(body="DIFFERENT"))
    assert exc.value.code == "idempotency_conflict"


def test_accept_stale_base(tmp_path: Path) -> None:
    conn = _db(tmp_path, last=5)
    with pytest.raises(AcceptError) as exc:
        accept_turn(conn, "claude", _req(expected_last_turn_id=0, processed_through_id=5))
    assert exc.value.code == "stale_base"


def test_accept_stale_read(tmp_path: Path) -> None:
    conn = _db(tmp_path, last=5)
    with pytest.raises(AcceptError) as exc:
        accept_turn(conn, "claude", _req(expected_last_turn_id=5, processed_through_id=3))
    assert exc.value.code == "stale_read"


def test_accept_not_baton(tmp_path: Path) -> None:
    conn = _db(tmp_path, baton="codex")
    with pytest.raises(AcceptError) as exc:
        accept_turn(conn, "claude", _req())
    assert exc.value.code == "not_baton"


def test_accept_requires_lease(tmp_path: Path) -> None:
    conn = _db(tmp_path, lease=False)
    with pytest.raises(AcceptError) as exc:
        accept_turn(conn, "claude", _req())
    assert exc.value.code == "lease_required"


def test_accept_rejects_inactive_thread(tmp_path: Path) -> None:
    conn = _db(tmp_path, status="needs_human", reason="disconnected")
    with pytest.raises(AcceptError) as exc:
        accept_turn(conn, "claude", _req())
    assert exc.value.code == "disconnected"


def test_accept_unknown_thread(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "router.db", SCHEMA_PATH)
    with pytest.raises(AcceptError) as exc:
        accept_turn(conn, "claude", _req())
    assert exc.value.code == "thread_not_found"


def test_flip_baton_guards_stale_base(tmp_path: Path) -> None:
    """The head UPDATE itself enforces the CAS base (defense in depth, not just check_cas)."""
    conn = _db(tmp_path, last=2)
    with pytest.raises(AcceptError) as exc:
        writes.flip_baton(conn, "t1", "codex", 3, expected_last_turn_id=0)
    assert exc.value.code == "stale_base"


def test_accept_rolls_back_on_gate_failure(tmp_path: Path) -> None:
    """Every AcceptError leaves no open transaction and no partial turn (rollback reliable)."""
    conn = _db(tmp_path, baton="codex")  # claude does not hold the baton -> not_baton
    with pytest.raises(AcceptError):
        accept_turn(conn, "claude", _req())
    assert conn.in_transaction is False
    assert conn.execute("SELECT COUNT(*) c FROM turns").fetchone()["c"] == 0
