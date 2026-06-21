"""Smoke helper: create a thread and hand the baton to codex so the WS wake fires.

Usage (from anywhere):  python scripts/smoke_wake.py [thread_id]
Reads the local bearer tokens from data/secrets.json; drives the turn as claude.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8000"
SECRETS = Path(__file__).resolve().parents[1] / "data" / "secrets.json"


def _post(path: str, token: str, body: dict) -> None:
    """POST one JSON body with bearer auth; exit with a readable message on error."""
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req).read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{path} failed: HTTP {exc.code} {exc.read().decode()}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"{path} failed: {exc.reason} (is the backend running?)")


def main() -> None:
    """Create the thread, lease it, and post a turn flipping the baton to codex."""
    thread = sys.argv[1] if len(sys.argv) > 1 else "wake1"
    token = json.loads(SECRETS.read_text())["agents"]["claude"]
    _post("/threads", token, {"thread_id": thread, "workspace_id": "local"})
    _post("/leases/acquire", token, {"thread_id": thread})
    _post(
        "/turns",
        token,
        {
            "thread_id": thread,
            "body": "wake smoke",
            "next_baton": "codex",
            "idempotency_key": f"smoke-{thread}",
            "expected_last_turn_id": 0,
            "processed_through_id": 0,
        },
    )
    print(f"OK -> thread '{thread}' is now codex's active turn; the extension should wake.")


if __name__ == "__main__":
    main()
