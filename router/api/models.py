"""Pydantic response models for the read-side API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Health(BaseModel):
    """GET /health response."""

    status: str
    schema_version: int


class ThreadView(BaseModel):
    """A thread's routing state (GET /threads/{thread_id})."""

    thread_id: str
    status: str
    status_reason: str | None
    baton: str | None
    last_turn_id: int
    workspace_id: str
    created_at: str


class ThreadCreate(BaseModel):
    """POST /threads request body."""

    thread_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    initial_baton: str | None = Field(default=None, min_length=1)


class ThreadStatusUpdate(BaseModel):
    """POST /threads/{thread_id}/status request body."""

    status: str
    status_reason: str | None = Field(default=None, min_length=1)


class EventView(BaseModel):
    """One turn in the events stream (GET /events) and the POST /turns response."""

    id: int
    thread_id: str
    author: str
    reply_to: int | None
    ts: str
    body: str


class WakeEvent(BaseModel):
    """WS push payload for an active thread whose baton reached the agent."""

    thread_id: str
    status: str
    status_reason: str | None
    baton: str | None
    last_turn_id: int


class TurnSubmission(BaseModel):
    """POST /turns request body. auth_agent comes from the token, never this body."""

    thread_id: str = Field(min_length=1)
    body: str = Field(min_length=1)
    reply_to: int | None = Field(default=None, ge=0)
    next_baton: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    expected_last_turn_id: int = Field(ge=0)
    processed_through_id: int = Field(ge=0)


class HaltSubmission(TurnSubmission):
    """POST /turns/halt: a normal turn plus the halt status it atomically flips to."""

    status: str = Field(min_length=1)
    status_reason: str | None = Field(default=None, min_length=1)


class ResumeSubmission(TurnSubmission):
    """POST /turns/resume: the operator's answer; next_baton is the agent to re-wake."""


class LeaseAcquire(BaseModel):
    """POST /leases/acquire request body."""

    thread_id: str = Field(min_length=1)
    ttl_seconds: int = Field(default=300, ge=1, le=3600)


class LeaseRenew(BaseModel):
    """POST /leases/renew request body."""

    thread_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    ttl_seconds: int = Field(default=300, ge=1, le=3600)


class LeaseRelease(BaseModel):
    """POST /leases/release request body."""

    thread_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)


class LeaseView(BaseModel):
    """Lease response body."""

    lease_id: str
    thread_id: str
    agent: str
    acquired_at: str
    expires_at: str
    heartbeat_at: str | None
    status: str


class LeaseSweepView(BaseModel):
    """POST /leases/sweep response body."""

    expired_leases: int
    threads_disconnected: int
