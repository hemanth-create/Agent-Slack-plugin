"""Tests for POST /turns/halt and /turns/resume: the atomic halt + resume HTTP path."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from router.api.app import app
from router.config.credentials import AgentTokens, write_tokens
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH

_CLAUDE = "c" * 40
_CODEX = "x" * 40
_CH = {"Authorization": f"Bearer {_CLAUDE}"}
_XH = {"Authorization": f"Bearer {_CODEX}"}
_FUTURE = "9999-12-31T23:59:59+00:00"
_HALT = {
    "thread_id": "t1", "body": "I'm stuck", "next_baton": "claude",
    "idempotency_key": "h1", "expected_last_turn_id": 0, "processed_through_id": 0,
    "status": "needs_human", "status_reason": "recovery_required",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db = tmp_path / "router.db"
    conn = init_db(db, SCHEMA_PATH)
    conn.execute(
        "INSERT INTO threads(thread_id, status, baton, last_turn_id, workspace_id, "
        "created_at) VALUES('t1','active','claude',0,'ws','now')"
    )
    conn.execute(
        "INSERT INTO leases(lease_id, thread_id, agent, acquired_at, expires_at, status) "
        "VALUES('L1','t1','claude','now',?,'active')",
        (_FUTURE,),
    )
    conn.close()
    secrets = tmp_path / "secrets.json"
    write_tokens(secrets, AgentTokens(agents={"claude": _CLAUDE, "codex": _CODEX}))
    monkeypatch.setattr("router.api.app.DB_PATH", db)
    monkeypatch.setattr("router.api.app.SECRETS_PATH", secrets)
    with TestClient(app) as test_client:
        yield test_client


def test_halt_requires_auth(client: TestClient) -> None:
    assert client.post("/turns/halt", json=_HALT).status_code == 401


def test_halt_flips_thread_off_active(client: TestClient) -> None:
    resp = client.post("/turns/halt", json=_HALT, headers=_CH)
    assert resp.status_code == 200 and resp.json()["author"] == "claude"
    state = client.get("/threads/t1", headers=_CH).json()
    assert state["status"] == "needs_human" and state["baton"] == "claude"
    assert state["last_turn_id"] == resp.json()["id"]


def test_halt_bad_status_is_structured_400(client: TestClient) -> None:
    resp = client.post("/turns/halt", json={**_HALT, "status": "continue"}, headers=_CH)
    assert resp.status_code == 400 and resp.json()["error"] == "invalid_status"


def test_resume_reactivates_after_halt(client: TestClient) -> None:
    halt = client.post("/turns/halt", json=_HALT, headers=_CH).json()
    resume = {
        "thread_id": "t1", "body": "here's the answer", "next_baton": "claude",
        "idempotency_key": "r1", "expected_last_turn_id": halt["id"],
        "processed_through_id": halt["id"],
    }
    resp = client.post("/turns/resume", json=resume, headers=_XH)  # codex acts as operator
    assert resp.status_code == 200 and resp.json()["author"] == "codex"
    state = client.get("/threads/t1", headers=_CH).json()
    assert state["status"] == "active" and state["status_reason"] is None
    assert state["baton"] == "claude" and state["last_turn_id"] == resp.json()["id"]


def test_resume_on_active_thread_is_409(client: TestClient) -> None:
    resume = {
        "thread_id": "t1", "body": "x", "next_baton": "claude",
        "idempotency_key": "r2", "expected_last_turn_id": 0, "processed_through_id": 0,
    }
    resp = client.post("/turns/resume", json=resume, headers=_XH)
    assert resp.status_code == 409 and resp.json()["error"] == "not_resumable"
