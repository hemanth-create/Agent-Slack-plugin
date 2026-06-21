"""HTTP tests for lease acquire, renew, release, auth, and structured errors."""
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
_CLAUDE_HEADERS = {"Authorization": f"Bearer {_CLAUDE}"}
_CODEX_HEADERS = {"Authorization": f"Bearer {_CODEX}"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db = tmp_path / "router.db"
    conn = init_db(db, SCHEMA_PATH)
    conn.execute(
        "INSERT INTO threads(thread_id, status, baton, workspace_id, created_at) "
        "VALUES('t1','active','claude','ws','now')"
    )
    conn.close()
    secrets = tmp_path / "secrets.json"
    write_tokens(secrets, AgentTokens(agents={"claude": _CLAUDE, "codex": _CODEX}))
    monkeypatch.setattr("router.api.app.DB_PATH", db)
    monkeypatch.setattr("router.api.app.SECRETS_PATH", secrets)
    with TestClient(app) as test_client:
        yield test_client


def test_acquire_lease_requires_auth(client: TestClient) -> None:
    assert client.post("/leases/acquire", json={"thread_id": "t1"}).status_code == 401


def test_acquire_lease_created(client: TestClient) -> None:
    resp = client.post("/leases/acquire", json={"thread_id": "t1"}, headers=_CLAUDE_HEADERS)
    assert resp.status_code == 201
    assert resp.json()["agent"] == "claude"


def test_renew_and_release_lease(client: TestClient) -> None:
    lease = client.post(
        "/leases/acquire", json={"thread_id": "t1"}, headers=_CLAUDE_HEADERS
    ).json()
    renew = client.post(
        "/leases/renew",
        json={"thread_id": "t1", "lease_id": lease["lease_id"]},
        headers=_CLAUDE_HEADERS,
    )
    release = client.post(
        "/leases/release",
        json={"thread_id": "t1", "lease_id": lease["lease_id"]},
        headers=_CLAUDE_HEADERS,
    )
    assert renew.status_code == 200
    assert release.json()["status"] == "released"


def test_acquire_lease_conflict_is_structured(client: TestClient) -> None:
    client.post("/leases/acquire", json={"thread_id": "t1"}, headers=_CLAUDE_HEADERS)
    resp = client.post("/leases/acquire", json={"thread_id": "t1"}, headers=_CODEX_HEADERS)
    assert resp.status_code == 409
    assert resp.json()["error"] == "lease_conflict"


def test_acquire_lease_rejects_empty_thread_id(client: TestClient) -> None:
    resp = client.post("/leases/acquire", json={"thread_id": ""}, headers=_CLAUDE_HEADERS)
    assert resp.status_code == 422


def test_sweep_requires_auth(client: TestClient) -> None:
    assert client.post("/leases/sweep").status_code == 401


def test_sweep_returns_counts(client: TestClient) -> None:
    resp = client.post("/leases/sweep", headers=_CLAUDE_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"expired_leases": 0, "threads_disconnected": 0}
