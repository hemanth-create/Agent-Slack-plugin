from __future__ import annotations

from pathlib import Path

from wake_driver.driver import decide_next, drive_once, halt_thread
from wake_driver.reconcile import classify
from wake_driver.state import StateStore


def _after(status="active", baton="codex", last=6):
    return {"status": status, "baton": baton, "last_turn_id": last}


# ---- reconcile.classify ----------------------------------------------------

def test_classify_done_when_advanced_and_handed_off() -> None:
    assert classify(5, _after(baton="codex", last=6), "claude") == "done"


def test_classify_halted_when_thread_left_active() -> None:
    assert classify(5, _after(status="needs_human", last=6), "claude") == "halted"


def test_classify_no_submit_when_head_unchanged() -> None:
    assert classify(5, _after(last=5), "claude") == "no_submit"


def test_classify_self_baton_when_still_mine() -> None:
    assert classify(5, _after(baton="claude", last=6), "claude") == "self_baton"


# ---- driver.decide_next / drive_once --------------------------------------

def test_decide_next_mapping() -> None:
    assert decide_next("done") == "advance"
    assert decide_next("halted") == "wait"
    assert decide_next("no_submit") == "escalate"
    assert decide_next("self_baton") == "escalate"
    assert decide_next("???") == "escalate"  # unknown defaults to escalate (fail safe)


async def test_drive_once_runs_spawn_then_classifies_router_state() -> None:
    calls = []

    async def spawn() -> None:
        calls.append("spawn")

    async def status() -> dict:
        return _after(baton="codex", last=6)

    cls = await drive_once("claude", 5, spawn, status)
    assert calls == ["spawn"] and cls == "done"


# ---- state.StateStore ------------------------------------------------------

def test_state_store_seed_is_idempotent_and_advance_keeps_start(tmp_path: Path) -> None:
    s = StateStore(tmp_path / "d" / "claude-t1.json")
    assert s.load() is None
    assert s.seed(7) == {"start_id": 7, "last_processed": 7}
    assert s.seed(99) == {"start_id": 7, "last_processed": 7}  # never resets the cap anchor
    s.advance(10)
    assert s.load() == {"start_id": 7, "last_processed": 10}


# ---- driver.halt_thread ----------------------------------------------------

class _FakeApi:
    def __init__(self, agent="claude"):
        self.agent_id = agent
        self.allowed = frozenset({"claude", "codex"})
        self.lease_ttl = 3000
        self.halted: dict | None = None
        self.released = False

    async def get_thread(self, tid):
        return {"thread_id": tid, "status": "active", "status_reason": None,
                "baton": self.agent_id, "last_turn_id": 0, "workspace_id": "ws",
                "created_at": "now"}

    async def acquire_lease(self, tid, ttl):
        return {"lease_id": "L", "thread_id": tid, "agent": self.agent_id,
                "acquired_at": "a", "expires_at": "e", "heartbeat_at": None, "status": "active"}

    async def get_events(self, tid, since=0):
        return []

    async def release_best_effort(self, tid, lid):
        self.released = True
        return True

    async def halt_turn(self, tid, body, key, exp, proc, status, reason):
        self.halted = {"status": status, "reason": reason, "body": body}
        return {"id": 9, "thread_id": tid, "author": self.agent_id,
                "reply_to": None, "ts": "now", "body": body}


async def test_halt_thread_blocks_with_invalid_submission() -> None:
    api = _FakeApi()
    await halt_thread(api, "t1", "escalate: self_baton")
    assert api.halted["status"] == "blocked"
    assert api.halted["reason"] == "invalid_submission"
    assert "escalate: self_baton" in api.halted["body"]
    assert api.released is True
