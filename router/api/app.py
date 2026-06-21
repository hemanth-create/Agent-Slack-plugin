"""FastAPI app: startup checks + token wiring + read-side endpoints."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status

from router.api.drain import drain_projections_best_effort
from router.api.errors import accept_error_handler
from router.api.lease_routes import lease_router
from router.api.models import EventView, Health, ThreadView, TurnSubmission
from router.api.thread_routes import thread_router
from router.api.turn_status_routes import turn_status_router
from router.api.ws_routes import ws_router
from router.auth import install_tokens, verify_api_key
from router.config.credentials import load_tokens, reverse_map
from router.config.startup_checks import assert_db_intact, assert_not_synced
from router.db import accept, reads
from router.db.connection import connect
from router.db.init_db import SCHEMA_VERSION, assert_schema_current
from router.errors import AcceptError
from router.paths import DB_PATH, PROJECTIONS_PATH, SECRETS_PATH


def ensure_db_ready(db_path: Path) -> None:
    """Fail closed unless an initialized, intact, current-schema DB exists."""
    assert_not_synced(db_path)
    if not db_path.exists():
        raise RuntimeError(f"{db_path} missing; run: python -m scripts.init_db")
    conn = connect(db_path)
    try:
        assert_db_intact(conn)
        assert_schema_current(conn)
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Refuse a synced/missing/stale DB, load tokens, open the single writer connection."""
    ensure_db_ready(DB_PATH)
    install_tokens(reverse_map(load_tokens(SECRETS_PATH)))
    app.state.db_path = DB_PATH
    app.state.projections_path = PROJECTIONS_PATH
    app.state.writer = connect(DB_PATH, check_same_thread=False)
    app.state.writer_lock = asyncio.Lock()
    try:
        yield
    finally:
        app.state.writer.close()


app = FastAPI(lifespan=lifespan)
app.add_exception_handler(AcceptError, accept_error_handler)
app.include_router(lease_router)
app.include_router(thread_router)
app.include_router(turn_status_router)
app.include_router(ws_router)


@app.get("/health", response_model=Health)
async def health() -> Health:
    """Liveness + schema version (no auth required)."""
    return Health(status="ok", schema_version=SCHEMA_VERSION)


@app.get("/threads/{thread_id}", response_model=ThreadView)
async def get_thread(thread_id: str, agent: str = Depends(verify_api_key)) -> ThreadView:
    """Return a thread's routing state (auth required)."""
    row = await asyncio.to_thread(reads.read_thread, DB_PATH, thread_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    return ThreadView(**dict(row))


@app.get("/events", response_model=list[EventView])
async def get_events(
    thread_id: str,
    since: int = Query(0, ge=0),
    agent: str = Depends(verify_api_key),
) -> list[EventView]:
    """Return turns for a thread with id > since (auth required)."""
    rows = await asyncio.to_thread(reads.read_thread_events, DB_PATH, thread_id, since)
    if rows is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    return [EventView(**dict(row)) for row in rows]


def _to_request(s: TurnSubmission) -> accept.TurnRequest:
    """Map the validated request body to the transaction's input dataclass."""
    return accept.TurnRequest(
        thread_id=s.thread_id,
        body=s.body,
        reply_to=s.reply_to,
        next_baton=s.next_baton,
        idempotency_key=s.idempotency_key,
        expected_last_turn_id=s.expected_last_turn_id,
        processed_through_id=s.processed_through_id,
    )


@app.post("/turns", response_model=EventView)
async def post_turn(
    submission: TurnSubmission,
    request: Request,
    response: Response,
    agent: str = Depends(verify_api_key),
) -> EventView:
    """Accept a turn through the single-writer transaction (auth required)."""
    async with request.app.state.writer_lock:
        outcome = await asyncio.to_thread(
            accept.accept_turn,
            request.app.state.writer,
            agent,
            _to_request(submission),
        )
    await drain_projections_best_effort(request)
    response.status_code = status.HTTP_201_CREATED if outcome.created else status.HTTP_200_OK
    return EventView(**outcome.turn)
