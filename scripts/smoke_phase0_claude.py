"""Phase-0.4 live smoke: one real headless claude turn = a zero-prompt relay round-trip.

Proves a spawned `claude -p` loads the relay MCP server (via the generated --mcp-config)
and calls relay_begin_turn + relay_submit_turn with NO permission prompt, advancing the
thread and handing the baton to codex. This is the #1 hands-free risk from the plan.

Needs the router running on 127.0.0.1:8000 and WAKE_CLAUDE_BIN set (claude is not on PATH):
    WAKE_CLAUDE_BIN="C:\\Users\\<you>\\.local\\bin\\claude.exe" python -m scripts.smoke_phase0_claude
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets as pysecrets
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "agent-relay"))
from server import relay_ops  # noqa: E402
from server.router_api import RouterApi  # noqa: E402

from wake_driver.local_config import secrets_path  # noqa: E402
from wake_driver.relay_config import write_relay_mcp_config  # noqa: E402
from wake_driver.spawn import _resolve_bin, claude_argv, prompt_for, run_turn  # noqa: E402

BASE = "http://127.0.0.1:8000"


async def main() -> None:
    toks = json.loads(secrets_path().read_text(encoding="utf-8"))["agents"]
    tid = "p04-" + pysecrets.token_hex(3)
    import httpx

    client = httpx.AsyncClient(base_url=BASE, headers={"Authorization": f"Bearer {toks['claude']}"})
    api = RouterApi(client, "claude", frozenset(toks), 3000)
    await relay_ops.start(api, "Greet your peer briefly and hand off.",
                          first_agent="claude", thread_id=tid)
    before = (await relay_ops.status(api, tid)).last_turn_id

    workdir = Path(tempfile.mkdtemp(prefix="p04-"))
    mcp = write_relay_mcp_config(workdir / "relay.json", "claude", BASE)
    argv = claude_argv(_resolve_bin(os.environ.get("WAKE_CLAUDE_BIN", "claude")), str(mcp))
    env = {**os.environ, "RELAY_API_KEY": toks["claude"], "MCP_TIMEOUT": "120000"}
    print(f"thread={tid} before_head={before}; spawning real claude ...")
    rc = await asyncio.to_thread(run_turn, argv, prompt_for(tid, "codex"), env, str(workdir), 300)

    after = await relay_ops.status(api, tid)
    print(f"exit={rc} | after: status={after.status} baton={after.baton} head={after.last_turn_id}")
    assert after.last_turn_id > before and after.baton == "codex", "no zero-prompt round-trip"
    print("PASS: headless claude completed a zero-prompt relay turn and handed off to codex")
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
