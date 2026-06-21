"""Durable driver state: start_id (cap anchor) + last_processed (de-dup), per (agent,thread).

Persisted so a crash-loop cannot reset the runaway cap by forgetting how many turns
have already happened (decision F: the cap is derived from durable router state).
"""
from __future__ import annotations

import json
from pathlib import Path


class StateStore:
    """Reads/writes {start_id, last_processed} for one (agent, thread) driver."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict | None:
        """Return the persisted state, or None if this driver has never enrolled."""
        if not self._path.exists():
            return None
        return json.loads(self._path.read_text(encoding="utf-8"))

    def seed(self, head: int) -> dict:
        """Initialize on first enroll only; an existing state is never reset."""
        existing = self.load()
        if existing is not None:
            return existing
        state = {"start_id": head, "last_processed": head}
        self._write(state)
        return state

    def advance(self, last_processed: int) -> None:
        """Record the latest handled head, preserving the original start_id."""
        state = self.load() or {"start_id": last_processed, "last_processed": last_processed}
        state["last_processed"] = last_processed
        self._write(state)

    def _write(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(state), encoding="utf-8")
