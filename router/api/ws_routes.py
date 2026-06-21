"""Loopback-only WS wake: push when an active thread's baton reaches the agent."""
from __future__ import annotations

import asyncio
import contextlib
import sqlite3

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.exceptions import HTTPException

from router.api.models import WakeEvent
from router.auth import verify_ws
from router.db import reads

ws_router = APIRouter()
POLL_SECONDS = 1.0
_POLICY_VIOLATION = 1008


def _wake(row: sqlite3.Row) -> WakeEvent:
    """Build the public wake frame from the current thread row."""
    return WakeEvent(
        thread_id=row["thread_id"],
        status=row["status"],
        status_reason=row["status_reason"],
        baton=row["baton"],
        last_turn_id=row["last_turn_id"],
    )


def _is_wake(row: sqlite3.Row, agent: str, last_pushed: int) -> bool:
    """Return whether this connection should receive a wake frame."""
    return (
        row["status"] == "active"
        and row["baton"] == agent
        and row["last_turn_id"] > last_pushed
    )


def _verify(websocket: WebSocket) -> str | None:
    """Resolve the WS agent or return None for a policy-violating handshake."""
    try:
        return verify_ws(
            websocket.headers.get("authorization"),
            websocket.headers.get("origin"),
        )
    except HTTPException:
        return None


async def _wait_disconnect(websocket: WebSocket) -> None:
    """Resolve when the client disconnects or sends a frame (a cancel signal).

    The watch loop never reads from the socket otherwise, so without this an
    idle client (one not holding the baton) could disconnect unnoticed and the
    loop would poll the DB forever.
    """
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        await websocket.receive()


async def _poll(websocket: WebSocket, agent: str, thread_id: str, closed: asyncio.Task) -> None:
    """Push a wake when the thread becomes the agent's active turn; stop if closed."""
    last_pushed = 0
    while not closed.done():
        row = await asyncio.to_thread(
            reads.read_thread, websocket.app.state.db_path, thread_id
        )
        if row is None:
            await websocket.close(code=_POLICY_VIOLATION)
            return
        if _is_wake(row, agent, last_pushed):
            await websocket.send_json(_wake(row).model_dump())
            last_pushed = row["last_turn_id"]
        await asyncio.wait({closed}, timeout=POLL_SECONDS)


@ws_router.websocket("/ws")
async def ws_wake(websocket: WebSocket, thread_id: str = Query(...)) -> None:
    """Push turn-wake frames to an authenticated agent watching one thread."""
    agent = _verify(websocket)
    if agent is None:
        await websocket.close(code=_POLICY_VIOLATION)
        return
    await websocket.accept()
    closed = asyncio.create_task(_wait_disconnect(websocket))
    try:
        await _poll(websocket, agent, thread_id, closed)
    except WebSocketDisconnect:
        pass
    finally:
        closed.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await closed
