"""Pydantic models the relay tools return (structured MCP output).

Field shapes mirror the router's read-side models so router rows splat in directly:
Event <- EventView, ThreadState <- ThreadView (extra thread fields are ignored).
"""
from __future__ import annotations

from pydantic import BaseModel


class Event(BaseModel):
    """One turn in the thread, as the router's GET /events emits it."""

    id: int
    thread_id: str
    author: str
    reply_to: int | None
    ts: str
    body: str


class NextTurn(BaseModel):
    """relay_start result: the freshly created thread's routing state."""

    thread_id: str
    baton: str
    last_turn_id: int


class TurnPrompt(BaseModel):
    """relay_begin_turn result: everything an agent needs to compose its turn."""

    thread_id: str
    expected_last_turn_id: int
    prior_events: list[Event]
    turn_token: str
    lease_expires_at: str


class SubmitResult(BaseModel):
    """relay_submit_turn result: the recorded turn id and the new baton."""

    turn_id: int
    created: bool
    baton: str


class ThreadState(BaseModel):
    """relay_status result: a thread's routing state (subset of ThreadView)."""

    thread_id: str
    status: str
    status_reason: str | None
    baton: str | None
    last_turn_id: int
