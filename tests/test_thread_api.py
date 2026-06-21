"""HTTP tests for POST /threads."""
from __future__ import annotations

from collections.abc import Iterator
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


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db = tmp_path / "router.db"
    init_db(db, SCHEMA_PATH).close()
    secrets = tmp_path / "secrets.json"
    write_tokens(secrets, AgentTokens(agents={"claude": _CLAUDE, "codex": _CODEX}))
    monkeypatch.setattr("router.api.app.DB_PATH", db)
    monkeypatch.setattr("router.api.app.SECRETS_PATH", secrets)
    with TestClient(app) as test_client:
        yield test_client


def test_create_thread_requires_auth(client: TestClient) -> None:
    resp = client.post("/threads", json={"thread_id": "t1", "workspace_id": "ws"})
    assert resp.status_code == 401


def test_create_thread_defaults_baton_to_creator(client: TestClient) -> None:
    resp = client.post(
        "/threads", json={"thread_id": "t1", "workspace_id": "ws"}, headers=_CLAUDE_HEADERS
    )
    assert resp.status_code == 201
    assert resp.json()["baton"] == "claude"
    assert resp.json()["last_turn_id"] == 0


def test_create_thread_accepts_known_initial_baton(client: TestClient) -> None:
    resp = client.post(
        "/threads",
        json={"thread_id": "t1", "workspace_id": "ws", "initial_baton": "codex"},
        headers=_CLAUDE_HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["baton"] == "codex"


def test_create_thread_duplicate_is_structured(client: TestClient) -> None:
    body = {"thread_id": "t1", "workspace_id": "ws"}
    client.post("/threads", json=body, headers=_CLAUDE_HEADERS)
    resp = client.post("/threads", json=body, headers=_CLAUDE_HEADERS)
    assert resp.status_code == 409
    assert resp.json()["error"] == "thread_exists"


def test_create_thread_rejects_unknown_baton(client: TestClient) -> None:
    resp = client.post(
        "/threads",
        json={"thread_id": "t1", "workspace_id": "ws", "initial_baton": "ghost"},
        headers=_CLAUDE_HEADERS,
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "unknown_baton"


def test_create_thread_rejects_empty_fields(client: TestClient) -> None:
    body = {"thread_id": "t1", "workspace_id": "ws", "initial_baton": "claude"}
    for field in ("thread_id", "workspace_id", "initial_baton"):
        resp = client.post(
            "/threads", json={**body, field: ""}, headers=_CLAUDE_HEADERS
        )
        assert resp.status_code == 422
