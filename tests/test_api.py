"""Tests for the read-side API: health, thread, events, and auth gating."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from router.api.app import app, ensure_db_ready
from router.auth import install_tokens
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH

_TOKEN = "t" * 40
_HEADERS = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db = tmp_path / "router.db"
    conn = init_db(db, SCHEMA_PATH)
    conn.execute(
        "INSERT INTO threads(thread_id, status, baton, workspace_id, created_at) "
        "VALUES('t1','active','claude','ws','now')"
    )
    conn.execute(
        "INSERT INTO turns(thread_id, author, ts, body, payload_hash) "
        "VALUES('t1','claude','now','hello','h')"
    )
    conn.close()
    monkeypatch.setattr("router.api.app.DB_PATH", db)
    install_tokens({_TOKEN: "claude"})
    return TestClient(app)


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_thread_requires_auth(client: TestClient) -> None:
    assert client.get("/threads/t1").status_code == 401


def test_thread_returns_state(client: TestClient) -> None:
    resp = client.get("/threads/t1", headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["baton"] == "claude"


def test_thread_missing_is_404(client: TestClient) -> None:
    assert client.get("/threads/nope", headers=_HEADERS).status_code == 404


def test_events_returns_turns(client: TestClient) -> None:
    resp = client.get("/events", params={"thread_id": "t1", "since": 0}, headers=_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1 and body[0]["body"] == "hello"


def test_events_rejects_negative_since(client: TestClient) -> None:
    resp = client.get("/events", params={"thread_id": "t1", "since": -1}, headers=_HEADERS)
    assert resp.status_code == 422


def test_events_missing_thread_is_404(client: TestClient) -> None:
    resp = client.get("/events", params={"thread_id": "nope", "since": 0}, headers=_HEADERS)
    assert resp.status_code == 404


def test_events_empty_for_caught_up_thread(client: TestClient) -> None:
    resp = client.get("/events", params={"thread_id": "t1", "since": 99}, headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []


def test_ensure_db_ready_refuses_missing(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        ensure_db_ready(tmp_path / "nope.db")
