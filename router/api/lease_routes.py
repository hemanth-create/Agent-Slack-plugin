"""HTTP routes for lease acquire, renew, and release."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request, status

from router.api.models import LeaseAcquire, LeaseRelease, LeaseRenew, LeaseSweepView, LeaseView
from router.auth import verify_api_key
from router.db import lease_sweep, leases

lease_router = APIRouter()


@lease_router.post(
    "/leases/acquire", response_model=LeaseView, status_code=status.HTTP_201_CREATED
)
async def acquire_lease(
    submission: LeaseAcquire,
    request: Request,
    agent: str = Depends(verify_api_key),
) -> LeaseView:
    """Acquire or extend the authenticated agent's compose lease."""
    async with request.app.state.writer_lock:
        row = await asyncio.to_thread(
            leases.acquire_lease,
            request.app.state.writer,
            agent,
            submission.thread_id,
            submission.ttl_seconds,
        )
    return LeaseView(**row)


@lease_router.post("/leases/renew", response_model=LeaseView)
async def renew_lease(
    submission: LeaseRenew,
    request: Request,
    agent: str = Depends(verify_api_key),
) -> LeaseView:
    """Heartbeat and extend the authenticated agent's active lease."""
    async with request.app.state.writer_lock:
        row = await asyncio.to_thread(
            leases.renew_lease,
            request.app.state.writer,
            agent,
            submission.thread_id,
            submission.lease_id,
            submission.ttl_seconds,
        )
    return LeaseView(**row)


@lease_router.post("/leases/release", response_model=LeaseView)
async def release_lease(
    submission: LeaseRelease,
    request: Request,
    agent: str = Depends(verify_api_key),
) -> LeaseView:
    """Release the authenticated agent's active lease."""
    async with request.app.state.writer_lock:
        row = await asyncio.to_thread(
            leases.release_lease,
            request.app.state.writer,
            agent,
            submission.thread_id,
            submission.lease_id,
        )
    return LeaseView(**row)


@lease_router.post("/leases/sweep", response_model=LeaseSweepView)
async def sweep_leases(
    request: Request,
    agent: str = Depends(verify_api_key),
) -> LeaseSweepView:
    """Expire overdue leases and disconnect abandoned active threads."""
    async with request.app.state.writer_lock:
        row = await asyncio.to_thread(
            lease_sweep.sweep_expired_leases,
            request.app.state.writer,
        )
    return LeaseSweepView(**row)
