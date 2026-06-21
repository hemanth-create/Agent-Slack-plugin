"""Dev helper to bootstrap the wake-driver loop manually (talks to the running router).

  python -m scripts.start_relay_thread create <thread_id> [first_agent]
      Create an active thread (baton = first_agent, default "claude"). Run this BEFORE
      starting the wake-drivers — a driver needs the thread to exist when it subscribes.

  python -m scripts.start_relay_thread kick <thread_id> "<opening message>"
      The current baton-holder posts one turn and hands off, starting the volley. Run this
      AFTER both wake-drivers are listening (a driver only wakes on a turn posted after it).

Tokens come from the resolved secrets file; the router is expected at http://127.0.0.1:8000.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "agent-relay"))
from server import relay_ops  # noqa: E402
from server.router_api import RouterApi  # noqa: E402

from wake_driver.local_config import secrets_path  # noqa: E402

BASE = "http://127.0.0.1:8000"
_OTHER = {"claude": "codex", "codex": "claude"}


def _tokens() -> dict[str, str]:
    return json.loads(secrets_path().read_text(encoding="utf-8"))["agents"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create(thread_id: str, first: str) -> None:
    toks = _tokens()
    async with httpx.AsyncClient(base_url=BASE, headers=_headers(toks[first])) as c:
        api = RouterApi(c, first, frozenset(toks), 3000)
        nxt = await relay_ops.start(api, f"Collaborate on {thread_id}.", first_agent=first,
                                    thread_id=thread_id)
    print(f"created {nxt.thread_id!r}: baton={nxt.baton} head={nxt.last_turn_id}")


async def _kick(thread_id: str, message: str) -> None:
    toks = _tokens()
    async with httpx.AsyncClient(base_url=BASE, headers=_headers(toks["claude"])) as c:
        holder = (await relay_ops.status(RouterApi(c, "claude", frozenset(toks), 3000), thread_id)).baton
    async with httpx.AsyncClient(base_url=BASE, headers=_headers(toks[holder])) as c:
        api = RouterApi(c, holder, frozenset(toks), 3000)
        prompt = await relay_ops.begin_turn(api, thread_id)
        res = await relay_ops.submit_turn(api, prompt.turn_token, message, next_baton=_OTHER[holder])
    print(f"kick: {holder} posted turn {res.turn_id} -> baton now {res.baton}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd, thread_id = sys.argv[1], sys.argv[2]
    if cmd == "create":
        asyncio.run(_create(thread_id, sys.argv[3] if len(sys.argv) > 3 else "claude"))
    elif cmd == "kick":
        msg = sys.argv[3] if len(sys.argv) > 3 else "Share one opening idea, then hand off."
        asyncio.run(_kick(thread_id, msg))
    else:
        print(f"unknown command {cmd!r}; use create|kick")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
