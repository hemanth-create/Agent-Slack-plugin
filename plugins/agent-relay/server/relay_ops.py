"""The five relay operations as plain async functions (api is injected, so tests mock it).

Guarantees baked in here: a double-read baton guard around lease acquire (TOCTOU),
local `next_baton` validation (a typo would permanently strand the thread), and a
single idempotent write per turn — all halts are in-body text, never a status call.
"""
from __future__ import annotations

from uuid import uuid4

from server.relay_models import Event, NextTurn, SubmitResult, ThreadState, TurnPrompt
from server.turn_token import decode, encode, mint


async def start(api, task, first_agent="claude", thread_id=None, workspace_id="ws") -> NextTurn:
    """Create a thread; the first agent opens by addressing `task` in its first turn."""
    if not task or not task.strip():
        raise ValueError("task (the collaboration brief) is required")
    if first_agent not in api.allowed:
        raise ValueError(f"unknown_first_agent: {first_agent!r}")
    row = await api.create_thread(thread_id or uuid4().hex, workspace_id, first_agent)
    return NextTurn(thread_id=row["thread_id"], baton=row["baton"],
                    last_turn_id=row["last_turn_id"])


async def begin_turn(api, thread_id) -> TurnPrompt:
    """Claim the turn: verify baton, take a lease, re-verify baton, read the thread."""
    thread = await api.get_thread(thread_id)
    if thread["status"] != "active" or thread["baton"] != api.agent_id:
        raise ValueError(f"not_your_turn: status={thread['status']} baton={thread['baton']}")
    lease = await api.acquire_lease(thread_id, api.lease_ttl)  # acquire never checks baton
    if lease["agent"] != api.agent_id:
        await api.release_best_effort(thread_id, lease["lease_id"])
        raise ValueError("lease_agent_mismatch")
    recheck = await api.get_thread(thread_id)  # TOCTOU guard
    if recheck["baton"] != api.agent_id:
        await api.release_best_effort(thread_id, lease["lease_id"])
        raise ValueError(f"baton_changed: now {recheck['baton']}")
    events = await api.get_events(thread_id, 0)
    expected = recheck["last_turn_id"]  # stable: only the baton-holder moves it
    token = mint(thread_id, lease["lease_id"], expected)
    return TurnPrompt(thread_id=thread_id, expected_last_turn_id=expected,
                      prior_events=[Event(**e) for e in events],
                      turn_token=encode(token), lease_expires_at=lease["expires_at"])


# Map a halt status to a valid schema status_reason (schema.sql enforces a fixed enum).
_HALT_REASONS = {"needs_human": "recovery_required", "blocked": "recovery_required"}


async def submit_turn(api, turn_token, body, next_baton, status="continue",
                      question=None) -> SubmitResult:
    """Record a CONTINUE turn (single idempotent write) and hand the baton to `next_baton`.

    Halts go through halt_turn: flipping thread status needs one atomic router txn, so
    submit_turn refuses any non-continue status rather than silently leaving it active.
    """
    if status != "continue":
        raise ValueError(f"use relay_halt_turn for status={status!r}; submit_turn only hands the baton")
    tok = decode(turn_token)
    if next_baton not in api.allowed:  # a typo would strand the thread (no re-baton tool)
        raise ValueError(f"unknown_next_baton: {next_baton!r}")
    created, turn = await api.post_turn(
        tok.thread_id, body, next_baton, tok.idempotency_key,
        tok.expected_last_turn_id, tok.expected_last_turn_id,  # processed == expected
    )
    await api.release_best_effort(tok.thread_id, tok.lease_id)  # swallows lease_not_active
    return SubmitResult(turn_id=turn["id"], created=created, baton=next_baton)


async def halt_turn(api, turn_token, body, status="needs_human", question=None) -> SubmitResult:
    """Record the halting turn AND flip thread status in one atomic router txn (baton kept)."""
    if status not in _HALT_REASONS:
        raise ValueError(f"unknown_halt_status: {status!r} (use needs_human or blocked)")
    tok = decode(turn_token)
    text = f"{body}\n\n[{status}] {question or ''}".rstrip()
    turn = await api.halt_turn(
        tok.thread_id, text, tok.idempotency_key,
        tok.expected_last_turn_id, tok.expected_last_turn_id, status, _HALT_REASONS[status],
    )
    await api.release_best_effort(tok.thread_id, tok.lease_id)
    return SubmitResult(turn_id=turn["id"], created=True, baton=api.agent_id)


async def status(api, thread_id) -> ThreadState:
    """Read a thread's routing state (extra ThreadView fields are dropped)."""
    return ThreadState(**await api.get_thread(thread_id))


async def events(api, thread_id, since=0) -> list[Event]:
    """List the thread's turns after `since` (0 = from the start)."""
    return [Event(**e) for e in await api.get_events(thread_id, since)]
