"""HTTP route for creating router threads."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request, status

from router.api.drain import drain_projections_best_effort
from router.api.models import ThreadCreate, ThreadStatusUpdate, ThreadView
from router.auth import known_agents, verify_api_key
from router.db import threads
from router.errors import AcceptError

thread_router = APIRouter()


def _validated_baton(submission: ThreadCreate, agent: str) -> str:
    """Return the requested baton after checking it is an installed agent."""
    baton = submission.initial_baton or agent
    if baton not in known_agents():
        raise AcceptError("unknown_baton", 400)
    return baton


def _validated_status(submission: ThreadStatusUpdate) -> tuple[str, str | None]:
    """Return a coherent terminal/paused status pair or raise a structured error."""
    return threads.validate_status_update(submission.status, submission.status_reason)


@thread_router.post("/threads", response_model=ThreadView, status_code=status.HTTP_201_CREATED)
async def create_thread(
    submission: ThreadCreate,
    request: Request,
    agent: str = Depends(verify_api_key),
) -> ThreadView:
    """Create an active thread through the single writer."""
    baton = _validated_baton(submission, agent)
    async with request.app.state.writer_lock:
        row = await asyncio.to_thread(
            threads.create_thread,
            request.app.state.writer,
            submission.thread_id,
            submission.workspace_id,
            baton,
        )
    return ThreadView(**row)


@thread_router.post("/threads/{thread_id}/status", response_model=ThreadView)
async def update_thread_status(
    thread_id: str,
    submission: ThreadStatusUpdate,
    request: Request,
    agent: str = Depends(verify_api_key),
) -> ThreadView:
    """Move an active thread to a terminal or paused status."""
    new_status, reason = _validated_status(submission)
    async with request.app.state.writer_lock:
        row = await asyncio.to_thread(
            threads.set_thread_status,
            request.app.state.writer,
            thread_id,
            agent,
            new_status,
            reason,
        )
    await drain_projections_best_effort(request)
    return ThreadView(**row)
