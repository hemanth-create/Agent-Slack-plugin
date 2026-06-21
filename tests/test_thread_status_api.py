"""HTTP tests for POST /threads/{thread_id}/status."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from router.api import app as app_module
from router.config.credentials import AgentTokens, write_tokens
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH

_CLAUDE = "c" * 40
_CODEX = "x" * 40
_CLAUDE_HEADERS = {"Authorization": f"Bearer {_CLAUDE}"}


@pytest.fixture
def client_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Path, Path]]:
    db = tmp_path / "router.db"
    projections = tmp_path / "projections"
    init_db(db, SCHEMA_PATH).close()
    secrets = tmp_path / "secrets.json"
    write_tokens(secrets, AgentTokens(agents={"claude": _CLAUDE, "codex": _CODEX}))
    monkeypatch.setattr(app_module, "DB_PATH", db)
    monkeypatch.setattr(app_module, "SECRETS_PATH", secrets)
    monkeypatch.setattr(app_module, "PROJECTIONS_PATH", projections)
    with TestClient(app_module.app) as client:
        yield client, db, projections


def test_update_status_requires_auth(client_state: tuple[TestClient, Path, Path]) -> None:
    client, _, _ = client_state
    resp = client.post("/threads/t1/status", json={"status": "done"})
    assert resp.status_code == 401


def test_update_done_clears_baton(client_state: tuple[TestClient, Path, Path]) -> None:
    client, _, _ = client_state
    _create(client)
    _acquire(client)
    resp = _set_status(client, "done")
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    assert resp.json()["baton"] is None


def test_update_needs_human_preserves_baton(
    client_state: tuple[TestClient, Path, Path]
) -> None:
    client, _, _ = client_state
    _create(client)
    _acquire(client)
    resp = _set_status(client, "needs_human", "recovery_required")
    assert resp.status_code == 200
    assert resp.json()["status_reason"] == "recovery_required"
    assert resp.json()["baton"] == "claude"


def test_update_status_rejects_not_baton(
    client_state: tuple[TestClient, Path, Path]
) -> None:
    client, _, _ = client_state
    _create(client, baton="codex")
    _acquire(client)
    resp = _set_status(client, "done")
    assert resp.status_code == 409
    assert resp.json()["error"] == "not_baton"


def test_update_status_requires_lease(client_state: tuple[TestClient, Path, Path]) -> None:
    client, _, _ = client_state
    _create(client)
    resp = _set_status(client, "done")
    assert resp.status_code == 409
    assert resp.json()["error"] == "lease_required"


def test_update_status_rejects_static_invalid_pairs(
    client_state: tuple[TestClient, Path, Path]
) -> None:
    client, _, _ = client_state
    cases = [
        ({"status": "active"}, 400, "invalid_status"),
        ({"status": "done", "status_reason": "user_cancelled"}, 400, "invalid_status"),
        ({"status": "blocked"}, 400, "reason_required"),
        ({"status": "blocked", "status_reason": "bad_reason"}, 400, "invalid_status"),
    ]
    for body, status_code, error in cases:
        resp = client.post("/threads/t1/status", json=body, headers=_CLAUDE_HEADERS)
        assert resp.status_code == status_code
        assert resp.json()["error"] == error


def test_update_status_rejects_empty_reason(
    client_state: tuple[TestClient, Path, Path]
) -> None:
    client, _, _ = client_state
    resp = client.post(
        "/threads/t1/status",
        json={"status": "blocked", "status_reason": ""},
        headers=_CLAUDE_HEADERS,
    )
    assert resp.status_code == 422


def test_update_status_rejects_already_terminal(
    client_state: tuple[TestClient, Path, Path]
) -> None:
    client, _, _ = client_state
    _create(client)
    _acquire(client)
    _set_status(client, "done")
    resp = _set_status(client, "done")
    assert resp.status_code == 409
    assert resp.json()["error"] == "not_active"


def _create(client: TestClient, baton: str | None = None) -> None:
    body = {"thread_id": "t1", "workspace_id": "ws"}
    if baton is not None:
        body["initial_baton"] = baton
    resp = client.post("/threads", json=body, headers=_CLAUDE_HEADERS)
    assert resp.status_code == 201


def _acquire(client: TestClient) -> None:
    resp = client.post(
        "/leases/acquire", json={"thread_id": "t1"}, headers=_CLAUDE_HEADERS
    )
    assert resp.status_code == 201


def _set_status(client: TestClient, status: str, reason: str | None = None) -> object:
    body = {"status": status}
    if reason is not None:
        body["status_reason"] = reason
    return client.post("/threads/t1/status", json=body, headers=_CLAUDE_HEADERS)
