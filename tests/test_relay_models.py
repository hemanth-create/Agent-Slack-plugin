from __future__ import annotations

from server.relay_models import Event, NextTurn, SubmitResult, ThreadState, TurnPrompt

# A row exactly as the router's EventView / GET /events emits it.
_EVENT_ROW = {
    "id": 3, "thread_id": "t1", "author": "claude",
    "reply_to": None, "ts": "2026-06-20T00:00:00Z", "body": "hi",
}
# A row exactly as the router's ThreadView / GET /threads/{id} emits it (superset).
_THREAD_ROW = {
    "thread_id": "t1", "status": "active", "status_reason": None,
    "baton": "codex", "last_turn_id": 3,
    "workspace_id": "ws", "created_at": "2026-06-20T00:00:00Z",
}


def test_event_parses_a_router_row() -> None:
    ev = Event(**_EVENT_ROW)
    assert ev.id == 3
    assert ev.author == "claude"
    assert ev.reply_to is None


def test_thread_state_ignores_extra_thread_fields() -> None:
    # ThreadView carries workspace_id/created_at the agent does not need; drop them.
    state = ThreadState(**_THREAD_ROW)
    assert state.baton == "codex"
    assert state.last_turn_id == 3
    assert not hasattr(state, "workspace_id")


def test_turn_prompt_holds_typed_events() -> None:
    prompt = TurnPrompt(
        thread_id="t1", expected_last_turn_id=3,
        prior_events=[Event(**_EVENT_ROW)],
        turn_token="tok", lease_expires_at="2026-06-20T01:00:00Z",
    )
    assert prompt.prior_events[0].body == "hi"
    assert prompt.turn_token == "tok"


def test_next_turn_and_submit_result_construct() -> None:
    nxt = NextTurn(thread_id="t1", baton="claude", last_turn_id=0)
    res = SubmitResult(turn_id=4, created=True, baton="codex")
    assert nxt.baton == "claude"
    assert res.created is True
    assert res.turn_id == 4
