"""Projection behavior tests for POST /threads/{thread_id}/status."""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from router.api import app as app_module
from router.api import drain as drain_module
from router.config.credentials import AgentTokens, write_tokens
from router.db.connection import connect
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH

_CLAUDE = "c" * 40
_CODEX = "x" * 40
_HEADERS = {"Authorization": f"Bearer {_CLAUDE}"}


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


def test_status_update_renders_terminal_projection(
    client_state: tuple[TestClient, Path, Path]
) -> None:
    client, _, projections = client_state
    _create_and_acquire(client)
    resp = _set_done(client)
    thread_md = (projections / "t1" / "thread.md").read_text(encoding="utf-8")
    state = _projection_state(projections)
    assert resp.status_code == 200
    assert "status: done" in thread_md
    assert state["status"] == "done" and state["baton"] is None


def test_status_commit_survives_projection_drain_failure(
    client_state: tuple[TestClient, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db, _ = client_state
    _create_and_acquire(client)

    async def fail_drain(*_args: object) -> int:
        raise RuntimeError("forced drain failure")

    monkeypatch.setattr(drain_module, "drain_dirty", fail_drain)
    resp = _set_done(client)
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    assert _dirty_flag(db) == 1


def _create_and_acquire(client: TestClient) -> None:
    create = client.post(
        "/threads", json={"thread_id": "t1", "workspace_id": "ws"}, headers=_HEADERS
    )
    lease = client.post("/leases/acquire", json={"thread_id": "t1"}, headers=_HEADERS)
    assert create.status_code == 201
    assert lease.status_code == 201


def _set_done(client: TestClient) -> object:
    return client.post("/threads/t1/status", json={"status": "done"}, headers=_HEADERS)


def _projection_state(projections: Path) -> dict:
    text = (projections / "t1" / "state.json").read_text(encoding="utf-8")
    return dict(json.loads(text))


def _dirty_flag(db: Path) -> int:
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT dirty FROM projections_dirty WHERE thread_id='t1'"
        ).fetchone()
        return int(row["dirty"])
    finally:
        conn.close()
