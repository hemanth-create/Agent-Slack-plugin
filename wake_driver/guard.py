"""Level-trigger guard: decide whether a wake/state means 'take a turn now'.

Mirrors the router wake predicate (status active AND baton mine) and adds the two
driver-side bounds: de-dup by head (never re-drive the same turn) and a durable
max-turn cap (runaway stop). Pure function: the driver feeds it relay_status truth.
"""
from __future__ import annotations


def should_act(state: dict, me: str, last_processed: int, start_id: int, cap: int) -> str:
    """Return 'act', 'idle', or 'halt_cap' for the current thread state.

    state needs status/baton/last_turn_id (a WakeEvent or relay_status both fit).
    last_processed: the head this driver already handled (de-dup). start_id: the head
    when this driver enrolled; cap bounds turns since then so a loop cannot run forever.
    """
    if state["status"] != "active" or state["baton"] != me:
        return "idle"
    if state["last_turn_id"] <= last_processed:  # duplicate / per-poll re-fire
        return "idle"
    if state["last_turn_id"] - start_id >= cap:  # runaway stop (durable, not in-memory)
        return "halt_cap"
    return "act"
