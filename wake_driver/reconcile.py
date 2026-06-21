"""Classify a spawn's outcome from authoritative router state (never CLI stdout).

The router cannot lie about whether a turn landed; a spawned model's stdout can be
truncated or malformed. So after every spawn the driver re-reads relay_status and
decides here whether the turn was good, a halt, a no-op, or a self-baton runaway.
"""
from __future__ import annotations


def classify(before_head: int, after: dict, me: str) -> str:
    """Return 'done', 'halted', 'no_submit', or 'self_baton' for one spawn's result."""
    if after["status"] != "active":
        return "halted"                       # agent halted (or a sweep halted) the thread
    if after["last_turn_id"] <= before_head:
        return "no_submit"                    # head did not move -> nothing was written
    if after["baton"] == me:
        return "self_baton"                   # advanced but still mine -> runaway risk
    return "done"                             # advanced + baton handed off -> a good turn
