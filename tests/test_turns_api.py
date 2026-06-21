"""Tests for POST /turns over HTTP: auth gate, created/replay status, structured error."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from router.api.app import app
from router.config.credentials import AgentTokens, write_tokens
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH

_TOKEN = "t" * 40
_HEADERS = {"Authorization": f"Bearer {_TOKEN}"}
_FUTURE = "9999-12-31T23:59:59+00:00"
_BODY = {
    "thread_id": "t1", "body": "hello", "next_baton": "codex",
    "idempotency_key": "k1", "expected_last_turn_id": 0, "processed_through_id": 0,
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
    write_tokens(secrets, AgentTokens(agents={"claude": _TOKEN}))
    monkeypatch.setattr("router.api.app.DB_PATH", db)
    monkeypatch.setattr("router.api.app.SECRETS_PATH", secrets)
    with TestClient(app) as test_client:
        yield test_client


def test_post_turn_requires_auth(client: TestClient) -> None:
    assert client.post("/turns", json=_BODY).status_code == 401


def test_post_turn_created(client: TestClient) -> None:
    resp = client.post("/turns", json=_BODY, headers=_HEADERS)
    assert resp.status_code == 201
    assert resp.json()["author"] == "claude" and resp.json()["body"] == "hello"


def test_post_turn_replay_is_200(client: TestClient) -> None:
    client.post("/turns", json=_BODY, headers=_HEADERS)
    resp = client.post("/turns", json=_BODY, headers=_HEADERS)
    assert resp.status_code == 200


def test_post_turn_structured_error(client: TestClient) -> None:
    resp = client.post("/turns", json={**_BODY, "expected_last_turn_id": 99}, headers=_HEADERS)
    assert resp.status_code == 409
    assert resp.json()["error"] == "stale_base"


def test_post_turn_rejects_empty_required_strings(client: TestClient) -> None:
    for field in ("thread_id", "body", "next_baton", "idempotency_key"):
        resp = client.post("/turns", json={**_BODY, field: ""}, headers=_HEADERS)
        assert resp.status_code == 422


def test_post_turn_rejects_negative_ids(client: TestClient) -> None:
    for field in ("reply_to", "expected_last_turn_id", "processed_through_id"):
        resp = client.post("/turns", json={**_BODY, field: -1}, headers=_HEADERS)
        assert resp.status_code == 422
