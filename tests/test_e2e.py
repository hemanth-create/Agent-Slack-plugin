"""End-to-end TestClient coverage for live turn acceptance and projections."""
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
_CLAUDE_HEADERS = {"Authorization": f"Bearer {_CLAUDE}"}
_CODEX_HEADERS = {"Authorization": f"Bearer {_CODEX}"}


@pytest.fixture
def e2e_client(
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
        _create_thread(client)
        yield client, db, projections


def test_turns_path_drains_projections_end_to_end(
    e2e_client: tuple[TestClient, Path, Path]
) -> None:
    client, _, projections = e2e_client
    claude_lease = _acquire(client, _CLAUDE_HEADERS)
    first = _post_turn(client, _CLAUDE_HEADERS, "k1", 0, 0, "hello from claude", "codex")
    assert first.status_code == 201
    assert _thread(client, _CLAUDE_HEADERS)["baton"] == "codex"

    _release(client, _CLAUDE_HEADERS, claude_lease)
    _acquire(client, _CODEX_HEADERS)
    second = _post_turn(client, _CODEX_HEADERS, "k2", 1, 1, "hello from codex", "claude")

    assert second.status_code == 201
    assert _thread(client, _CODEX_HEADERS)["baton"] == "claude"
    assert _event_bodies(client, _CODEX_HEADERS) == ["hello from claude", "hello from codex"]
    _assert_projection(projections, last_turn_id=2)


def test_post_turn_keeps_commit_when_projection_drain_fails(
    e2e_client: tuple[TestClient, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db, _ = e2e_client
    _acquire(client, _CLAUDE_HEADERS)

    async def fail_drain(*_args: object) -> int:
        raise RuntimeError("forced drain failure")

    monkeypatch.setattr(drain_module, "drain_dirty", fail_drain)
    resp = _post_turn(client, _CLAUDE_HEADERS, "k1", 0, 0, "committed", "codex")

    assert resp.status_code == 201
    assert _event_bodies(client, _CLAUDE_HEADERS) == ["committed"]
    assert _dirty_flag(db) == 1


def _create_thread(client: TestClient) -> None:
    resp = client.post(
        "/threads", json={"thread_id": "t1", "workspace_id": "ws"}, headers=_CLAUDE_HEADERS
    )
    assert resp.status_code == 201


def _acquire(client: TestClient, headers: dict[str, str]) -> str:
    resp = client.post("/leases/acquire", json={"thread_id": "t1"}, headers=headers)
    assert resp.status_code == 201
    return str(resp.json()["lease_id"])


def _release(client: TestClient, headers: dict[str, str], lease_id: str) -> None:
    resp = client.post(
        "/leases/release",
        json={"thread_id": "t1", "lease_id": lease_id},
        headers=headers,
    )
    assert resp.status_code == 200


def _post_turn(
    client: TestClient,
    headers: dict[str, str],
    key: str,
    expected: int,
    processed: int,
    body: str,
    next_baton: str,
) -> object:
    payload = {
        "thread_id": "t1",
        "body": body,
        "next_baton": next_baton,
        "idempotency_key": key,
        "expected_last_turn_id": expected,
        "processed_through_id": processed,
    }
    return client.post("/turns", json=payload, headers=headers)


def _thread(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    resp = client.get("/threads/t1", headers=headers)
    assert resp.status_code == 200
    return dict(resp.json())


def _event_bodies(client: TestClient, headers: dict[str, str]) -> list[str]:
    resp = client.get("/events", params={"thread_id": "t1"}, headers=headers)
    assert resp.status_code == 200
    return [str(event["body"]) for event in resp.json()]


def _assert_projection(projections: Path, last_turn_id: int) -> None:
    root = projections / "t1"
    thread_md = (root / "thread.md").read_text(encoding="utf-8")
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert "hello from claude" in thread_md and "hello from codex" in thread_md
    assert state["baton"] == "claude"
    assert state["last_turn_id"] == last_turn_id


def _dirty_flag(db: Path) -> int:
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT dirty FROM projections_dirty WHERE thread_id='t1'"
        ).fetchone()
        return int(row["dirty"])
    finally:
        conn.close()
