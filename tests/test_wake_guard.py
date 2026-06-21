from __future__ import annotations

from pathlib import Path

from wake_driver.guard import should_act
from wake_driver.lock import acquire_singleflight, release_singleflight


def _state(status="active", baton="claude", last=5):
    return {"status": status, "baton": baton, "last_turn_id": last}


def test_act_when_my_active_turn_advanced() -> None:
    assert should_act(_state(last=5), "claude", last_processed=4, start_id=0, cap=24) == "act"


def test_idle_when_not_my_baton() -> None:
    assert should_act(_state(baton="codex"), "claude", 0, 0, 24) == "idle"


def test_idle_when_not_active() -> None:
    assert should_act(_state(status="needs_human"), "claude", 0, 0, 24) == "idle"


def test_idle_on_duplicate_head() -> None:
    # already processed this head -> de-dup (per-poll re-fire, reconnect re-push)
    assert should_act(_state(last=5), "claude", last_processed=5, start_id=0, cap=24) == "idle"


def test_halt_cap_when_turns_since_start_exceed_cap() -> None:
    assert should_act(_state(last=30), "claude", last_processed=29, start_id=6, cap=24) == "halt_cap"


def test_act_just_below_cap() -> None:
    assert should_act(_state(last=29), "claude", last_processed=28, start_id=6, cap=24) == "act"


def test_singleflight_excludes_a_second_holder(tmp_path: Path) -> None:
    p = str(tmp_path / "t1-claude.lock")
    first = acquire_singleflight(p)
    assert first is not None
    assert acquire_singleflight(p) is None  # second driver blocked
    release_singleflight(first)
    again = acquire_singleflight(p)  # freed after release
    assert again is not None
    release_singleflight(again)
