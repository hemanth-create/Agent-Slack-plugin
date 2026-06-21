"""Per-turn driving core: run one spawn, then decide the next move from router state.

The spawn callable and the status reader are injected so this core is fully testable
without a live CLI; run.py wires the real subprocess + router client around it.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from server import relay_ops
from server.turn_token import decode

from wake_driver.reconcile import classify

# Turn classification -> driver action.
_NEXT = {"done": "advance", "halted": "wait", "no_submit": "escalate", "self_baton": "escalate"}


async def drive_once(
    me: str,
    before_head: int,
    spawn: Callable[[], Awaitable[None]],
    get_status: Callable[[], Awaitable[dict]],
) -> str:
    """Spawn one turn (injected), then classify the outcome from router state, not stdout."""
    await spawn()
    return classify(before_head, await get_status(), me)


def decide_next(classification: str) -> str:
    """Map a turn classification to the driver's next move (advance | wait | escalate)."""
    return _NEXT.get(classification, "escalate")


async def halt_thread(api, thread_id: str, note: str) -> None:
    """Stop the wake loop (escalate / cap): claim the turn and halt the thread as blocked."""
    prompt = await relay_ops.begin_turn(api, thread_id)
    tok = decode(prompt.turn_token)
    await api.halt_turn(
        tok.thread_id, f"[driver] {note}", tok.idempotency_key,
        tok.expected_last_turn_id, tok.expected_last_turn_id,
        "blocked", "invalid_submission",
    )
    await api.release_best_effort(tok.thread_id, tok.lease_id)
