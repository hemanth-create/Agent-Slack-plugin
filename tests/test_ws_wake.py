"""Tests for WS /ws agent-wake notifications."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from router.api import app as app_module
from router.api import ws_routes
from router.config.credentials import AgentTokens, write_tokens
from router.db.connection import connect
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH

_CLAUDE = "c" * 40
_CODEX = "x" * 40
_CODEX_WS = {"Authorization": f"Bearer {_CODEX}", "origin": "http://127.0.0.1"}
_CLAUDE_WS = {"Authorization": f"Bearer {_CLAUDE}", "origin": "http://127.0.0.1"}


@pytest.fixture
def client_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Path]]:
    db = tmp_path / "router.db"
    init_db(db, SCHEMA_PATH).close()
    secrets = tmp_path / "secrets.json"
    write_tokens(secrets, AgentTokens(agents={"claude": _CLAUDE, "codex": _CODEX}))
    monkeypatch.setattr(app_module, "DB_PATH", db)
    monkeypatch.setattr(app_module, "SECRETS_PATH", secrets)
    monkeypatch.setattr(ws_routes, "POLL_SECONDS", 0.01)
    with TestClient(app_module.app) as client:
        yield client, db


def test_ws_rejects_missing_origin(client_state: tuple[TestClient, Path]) -> None:
    client, db = client_state
    _set_thread(db, "active", "codex", 1)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            "/ws?thread_id=t1", headers={"Authorization": f"Bearer {_CODEX}"}
        ):
            pass
    assert exc.value.code == 1008


def test_ws_rejects_bad_bearer(client_state: tuple[TestClient, Path]) -> None:
    client, db = client_state
    _set_thread(db, "active", "codex", 1)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            "/ws?thread_id=t1",
            headers={"Authorization": "Bearer bad", "origin": "http://127.0.0.1"},
        ):
            pass
    assert exc.value.code == 1008


def test_ws_accepts_valid_handshake(client_state: tuple[TestClient, Path]) -> None:
    client, db = client_state
    _set_thread(db, "active", "claude", 0)
    with client.websocket_connect("/ws?thread_id=t1", headers=_CODEX_WS):
        pass


def test_ws_sends_immediate_active_turn(client_state: tuple[TestClient, Path]) -> None:
    client, db = client_state
    _set_thread(db, "active", "codex", 1)
    with client.websocket_connect("/ws?thread_id=t1", headers=_CODEX_WS) as ws:
        assert ws.receive_json() == _wake("active", None, "codex", 1)


def test_ws_sends_flip_to_you(client_state: tuple[TestClient, Path]) -> None:
    client, db = client_state
    _set_thread(db, "active", "claude", 1)
    with client.websocket_connect("/ws?thread_id=t1", headers=_CODEX_WS) as ws:
        _set_thread(db, "active", "codex", 2)
        assert ws.receive_json() == _wake("active", None, "codex", 2)


def test_ws_paused_baton_does_not_wake(client_state: tuple[TestClient, Path]) -> None:
    client, db = client_state
    _set_thread(db, "needs_human", "codex", 2, "recovery_required")
    with client.websocket_connect("/ws?thread_id=t1", headers=_CODEX_WS) as ws:
        time.sleep(0.05)  # several polls run on the paused thread
        _set_thread(db, "active", "codex", 3)
        # A correct route sends NO frame while paused, so the first frame must be
        # the active wake. A leaked paused frame would arrive first and fail here.
        assert ws.receive_json() == _wake("active", None, "codex", 3)


def test_ws_dedupes_unchanged_turn(client_state: tuple[TestClient, Path]) -> None:
    client, db = client_state
    _set_thread(db, "active", "codex", 2)
    with client.websocket_connect("/ws?thread_id=t1", headers=_CODEX_WS) as ws:
        assert ws.receive_json() == _wake("active", None, "codex", 2)
        time.sleep(0.05)  # unchanged state: a duplicate wake would be queued here
        _set_thread(db, "active", "codex", 3)
        # The next frame must be the new turn, not a re-send of turn 2.
        assert ws.receive_json() == _wake("active", None, "codex", 3)


def test_ws_unknown_thread_closes_1008(client_state: tuple[TestClient, Path]) -> None:
    client, _ = client_state
    with client.websocket_connect("/ws?thread_id=missing", headers=_CLAUDE_WS) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


def test_poll_exits_on_idle_disconnect(client_state: tuple[TestClient, Path]) -> None:
    """An idle watcher (baton elsewhere) that disconnects must stop the loop."""
    _, db = client_state
    _set_thread(db, "active", "claude", 1)  # baton not on codex -> no wake
    asyncio.run(_run_idle_then_close(db))


async def _run_idle_then_close(db: Path) -> None:
    gate = asyncio.Event()
    closed = asyncio.create_task(gate.wait())
    ws = _StubWS(db)
    poll = asyncio.create_task(ws_routes._poll(ws, "codex", "t1", closed))
    await asyncio.sleep(0.05)
    assert not poll.done()  # still watching while connected
    gate.set()  # simulate the client disconnecting
    await asyncio.wait_for(poll, 1.0)  # loop must exit promptly, not leak
    closed.cancel()
    assert ws.sent == []  # baton was never on codex


class _StubWS:
    """Minimal stand-in for a Starlette WebSocket used by `_poll` directly."""

    def __init__(self, db: Path) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(db_path=db))
        self.sent: list[dict[str, Any]] = []
        self.closed: int | None = None

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def close(self, code: int) -> None:
        self.closed = code


def _set_thread(
    db: Path, status: str, baton: str | None, last_turn_id: int, reason: str | None = None
) -> None:
    conn = connect(db)
    try:
        conn.execute("DELETE FROM threads WHERE thread_id = 't1'")
        conn.execute(
            "INSERT INTO threads(thread_id, status, status_reason, baton, last_turn_id, "
            "workspace_id, created_at) VALUES('t1', ?, ?, ?, ?, 'ws', 'now')",
            (status, reason, baton, last_turn_id),
        )
    finally:
        conn.close()


def _wake(
    status: str, reason: str | None, baton: str | None, last_turn_id: int
) -> dict[str, Any]:
    return {
        "thread_id": "t1",
        "status": status,
        "status_reason": reason,
        "baton": baton,
        "last_turn_id": last_turn_id,
    }
