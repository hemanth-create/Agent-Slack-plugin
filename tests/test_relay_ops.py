from __future__ import annotations

import pytest

from server import relay_mcp, relay_ops
from server.turn_token import decode

_THREAD = {
    "thread_id": "t1", "status": "active", "status_reason": None,
    "baton": "claude", "last_turn_id": 0, "workspace_id": "ws", "created_at": "now",
}
_LEASE = {
    "lease_id": "L", "thread_id": "t1", "agent": "claude",
    "acquired_at": "a", "expires_at": "e", "heartbeat_at": None, "status": "active",
}


class FakeApi:
    """Records call order and returns canned router rows (no HTTP)."""

    def __init__(self, agent_id="claude", recheck=None, lease=None, events=None, created=True):
        self.agent_id = agent_id
        self.allowed = frozenset({"claude", "codex"})
        self.lease_ttl = 3000
        self._recheck = recheck
        self._lease = lease or _LEASE
        self._events = [] if events is None else events
        self._created = created
        self.calls: list[str] = []
        self.posted: dict | None = None
        self._gets = 0

    async def create_thread(self, thread_id, workspace_id, initial_baton):
        self.calls.append("create_thread")
        return {**_THREAD, "thread_id": thread_id, "baton": initial_baton,
                "workspace_id": workspace_id}

    async def get_thread(self, thread_id):
        self.calls.append("get_thread")
        self._gets += 1
        if self._gets >= 2 and self._recheck is not None:
            return self._recheck
        return _THREAD

    async def acquire_lease(self, thread_id, ttl):
        self.calls.append("acquire_lease")
        return self._lease

    async def release_best_effort(self, thread_id, lease_id):
        self.calls.append("release")
        return True

    async def get_events(self, thread_id, since=0):
        self.calls.append("get_events")
        return self._events

    async def post_turn(self, thread_id, body, next_baton, key, expected, processed):
        self.calls.append("post_turn")
        self.posted = {"body": body, "next_baton": next_baton, "key": key,
                       "expected": expected, "processed": processed}
        return self._created, {"id": 1, "thread_id": thread_id, "author": self.agent_id,
                               "reply_to": None, "ts": "now", "body": body}

    async def halt_turn(self, thread_id, body, key, expected, processed, status, reason):
        self.calls.append("halt_turn")
        self.halted = {"body": body, "status": status, "reason": reason,
                       "expected": expected, "processed": processed}
        return {"id": 7, "thread_id": thread_id, "author": self.agent_id,
                "reply_to": None, "ts": "now", "body": body}


# ---- start ----------------------------------------------------------------

async def test_start_creates_thread_with_first_agent_as_baton() -> None:
    api = FakeApi()
    res = await relay_ops.start(api, "do the thing", first_agent="codex", thread_id="t9")
    assert res.thread_id == "t9"
    assert res.baton == "codex"
    assert api.calls == ["create_thread"]


async def test_start_rejects_empty_task_and_unknown_agent() -> None:
    api = FakeApi()
    with pytest.raises(ValueError):
        await relay_ops.start(api, "   ", first_agent="claude")
    with pytest.raises(ValueError):
        await relay_ops.start(api, "task", first_agent="ghost")


# ---- begin_turn -----------------------------------------------------------

async def test_begin_turn_acquires_after_baton_check_and_pins_token() -> None:
    api = FakeApi(events=[{"id": 1, "thread_id": "t1", "author": "codex",
                           "reply_to": None, "ts": "now", "body": "prior"}])
    prompt = await relay_ops.begin_turn(api, "t1")
    # baton verified before the lease is taken:
    assert api.calls.index("get_thread") < api.calls.index("acquire_lease")
    # double-read TOCTOU guard => two get_thread calls:
    assert api.calls.count("get_thread") == 2
    tok = decode(prompt.turn_token)
    assert tok.lease_id == "L"
    assert tok.expected_last_turn_id == 0
    assert prompt.prior_events[0].body == "prior"


async def test_begin_turn_rejects_when_not_my_baton_before_acquire() -> None:
    api = FakeApi(agent_id="codex")  # thread baton is "claude"
    with pytest.raises(ValueError, match="not_your_turn"):
        await relay_ops.begin_turn(api, "t1")
    assert "acquire_lease" not in api.calls


async def test_begin_turn_releases_on_baton_changed_recheck() -> None:
    moved = {**_THREAD, "baton": "codex"}
    api = FakeApi(recheck=moved)
    with pytest.raises(ValueError, match="baton_changed"):
        await relay_ops.begin_turn(api, "t1")
    assert "release" in api.calls  # lease handed back, not stranded


async def test_begin_turn_releases_on_lease_agent_mismatch() -> None:
    api = FakeApi(lease={**_LEASE, "agent": "codex"})
    with pytest.raises(ValueError, match="lease_agent_mismatch"):
        await relay_ops.begin_turn(api, "t1")
    assert "release" in api.calls


# ---- submit_turn ----------------------------------------------------------

def _token() -> str:
    from server.turn_token import encode, mint
    return encode(mint("t1", "L", 0))


async def test_submit_turn_pins_key_sets_baton_and_releases() -> None:
    api = FakeApi()
    res = await relay_ops.submit_turn(api, _token(), "my analysis", next_baton="codex")
    assert res.baton == "codex"
    assert res.created is True
    assert api.posted["expected"] == api.posted["processed"] == 0
    assert api.posted["key"].startswith("t1:0:")
    assert api.calls[-1] == "release"


async def test_submit_turn_rejects_unknown_next_baton_before_post() -> None:
    api = FakeApi()
    with pytest.raises(ValueError, match="unknown_next_baton"):
        await relay_ops.submit_turn(api, _token(), "x", next_baton="ghost")
    assert "post_turn" not in api.calls


async def test_submit_turn_rejects_non_continue_status() -> None:
    # Decision E: status flips must go through relay_halt_turn (one atomic txn).
    api = FakeApi()
    with pytest.raises(ValueError, match="relay_halt_turn"):
        await relay_ops.submit_turn(api, _token(), "stuck", next_baton="codex",
                                    status="needs_human", question="which DB?")
    assert "post_turn" not in api.calls


async def test_halt_turn_posts_atomic_halt_and_releases() -> None:
    api = FakeApi()
    res = await relay_ops.halt_turn(api, _token(), "I'm stuck",
                                    status="needs_human", question="which DB?")
    assert api.halted["status"] == "needs_human"
    assert api.halted["reason"] == "recovery_required"      # mapped to a valid schema reason
    assert "[needs_human]" in api.halted["body"] and "which DB?" in api.halted["body"]
    assert api.halted["expected"] == api.halted["processed"] == 0
    assert res.baton == api.agent_id                        # halter keeps the baton
    assert api.calls[-1] == "release"


async def test_halt_turn_rejects_unknown_status() -> None:
    api = FakeApi()
    with pytest.raises(ValueError, match="unknown_halt_status"):
        await relay_ops.halt_turn(api, _token(), "x", status="done")
    assert "halt_turn" not in api.calls


async def test_submit_turn_replay_reports_not_created() -> None:
    api = FakeApi(created=False)
    res = await relay_ops.submit_turn(api, _token(), "x", next_baton="codex")
    assert res.created is False


# ---- status / events ------------------------------------------------------

async def test_status_returns_thread_state_subset() -> None:
    api = FakeApi()
    state = await relay_ops.status(api, "t1")
    assert state.baton == "claude"
    assert not hasattr(state, "workspace_id")


# ---- env fail-fast --------------------------------------------------------

def test_build_api_fails_fast_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("RELAY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="RELAY_API_KEY"):
        relay_mcp.build_api()


def test_build_api_succeeds_with_api_key(monkeypatch) -> None:
    monkeypatch.setenv("RELAY_API_KEY", "secret")
    monkeypatch.setenv("RELAY_AGENT_ID", "codex")
    api = relay_mcp.build_api()
    assert api.agent_id == "codex"
    assert "codex" in api.allowed
