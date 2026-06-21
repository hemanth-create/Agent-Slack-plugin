"""Live Phase-0.6 smoke: the wake_driver WS client receives a real /ws wake.

Subscribes as claude, has codex take a turn (flipping the baton to claude), and asserts
the wake_stream yields a baton=claude frame. Needs the router running on 127.0.0.1:8000.
Run:  python -m scripts.smoke_ws_listen
"""
from __future__ import annotations

import asyncio
import json
import secrets as pysecrets
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "agent-relay"))
from server import relay_ops  # noqa: E402
from server.router_api import RouterApi  # noqa: E402

from wake_driver.local_config import secrets_path  # noqa: E402
from wake_driver.ws_listen import wake_stream  # noqa: E402

BASE, WS = "http://127.0.0.1:8000", "ws://127.0.0.1:8000"


def _api(agent: str, toks: dict) -> RouterApi:
    client = httpx.AsyncClient(base_url=BASE, headers={"Authorization": f"Bearer {toks[agent]}"})
    return RouterApi(client, agent, frozenset(toks), 3000)


async def main() -> None:
    toks = json.loads(secrets_path().read_text(encoding="utf-8"))["agents"]
    tid = "wsprobe-" + pysecrets.token_hex(3)
    claude, codex = _api("claude", toks), _api("codex", toks)
    await relay_ops.start(claude, "probe", first_agent="codex", thread_id=tid)

    got: dict = {}

    async def listen() -> None:
        async for frame in wake_stream(WS, tid, toks["claude"]):
            got["frame"] = frame
            return

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.6)  # let the socket connect before we trigger the wake
    p = await relay_ops.begin_turn(codex, tid)
    await relay_ops.submit_turn(codex, p.turn_token, "codex here", next_baton="claude")
    await asyncio.wait_for(task, timeout=8)

    frame = got.get("frame")
    assert frame and frame["baton"] == "claude" and frame["status"] == "active", frame
    print(f"PASS: wake_stream received a real /ws wake -> {frame}")
    await claude.aclose()
    await codex.aclose()


if __name__ == "__main__":
    asyncio.run(main())
