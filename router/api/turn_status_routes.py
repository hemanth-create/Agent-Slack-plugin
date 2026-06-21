"""HTTP routes for the atomic halt and resume turn transitions (single writer)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request

from router.api.drain import drain_projections_best_effort
from router.api.models import EventView, HaltSubmission, ResumeSubmission
from router.auth import verify_api_key
from router.db import transitions
from router.db.accept import TurnRequest

turn_status_router = APIRouter()


def _to_request(s: HaltSubmission | ResumeSubmission) -> TurnRequest:
    """Map a validated submission body to the transaction's input dataclass."""
    return TurnRequest(
        thread_id=s.thread_id, body=s.body, reply_to=s.reply_to, next_baton=s.next_baton,
        idempotency_key=s.idempotency_key, expected_last_turn_id=s.expected_last_turn_id,
        processed_through_id=s.processed_through_id,
    )


@turn_status_router.post("/turns/halt", response_model=EventView)
async def post_halt(
    submission: HaltSubmission,
    request: Request,
    agent: str = Depends(verify_api_key),
) -> EventView:
    """Atomically record a halting turn and flip the thread off 'active' (auth required)."""
    async with request.app.state.writer_lock:
        turn = await asyncio.to_thread(
            transitions.accept_halt_turn, request.app.state.writer, agent,
            _to_request(submission), submission.status, submission.status_reason,
        )
    await drain_projections_best_effort(request)
    return EventView(**turn)


@turn_status_router.post("/turns/resume", response_model=EventView)
async def post_resume(
    submission: ResumeSubmission,
    request: Request,
    agent: str = Depends(verify_api_key),
) -> EventView:
    """Append the operator's answer and reactivate a halted thread (auth required)."""
    async with request.app.state.writer_lock:
        turn = await asyncio.to_thread(
            transitions.accept_resume_turn, request.app.state.writer, agent,
            _to_request(submission),
        )
    await drain_projections_best_effort(request)
    return EventView(**turn)
