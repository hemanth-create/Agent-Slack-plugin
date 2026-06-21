"""Live stdio-MCP smoke: drive the packaged relay server as two agents (claude + codex).

Launches server/relay_mcp.py exactly as .mcp.json does (subprocess, env config, FastMCP
stdio transport) with real tokens against the running router, and walks one full exchange.
Run with an interpreter that has `mcp` installed:  python -m scripts.smoke_relay_mcp
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from wake_driver.local_config import python_bin, secrets_path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "agent-relay"
TOOLS = {"relay_start", "relay_begin_turn", "relay_submit_turn", "relay_status", "relay_events"}


def params_for(agent: str, token: str) -> StdioServerParameters:
    env = {**os.environ, "RELAY_API_KEY": token, "RELAY_AGENT_ID": agent,
           "RELAY_ALLOWED_AGENTS": "claude,codex", "RELAY_BASE_URL": "http://127.0.0.1:8000"}
    return StdioServerParameters(command=python_bin(), args=["-m", "server.relay_mcp"],
                                 env=env, cwd=str(PLUGIN))


async def call(session: ClientSession, name: str, **args):
    res = await session.call_tool(name, args)
    if res.isError:
        raise RuntimeError(f"{name} -> {[c.text for c in res.content]}")
    data = res.structuredContent or {}
    return data.get("result", data)  # list returns are wrapped under "result"


async def main() -> None:
    agents = json.loads(secrets_path().read_text(encoding="utf-8"))["agents"]
    tid = "smoke-" + secrets.token_hex(3)
    async with stdio_client(params_for("claude", agents["claude"])) as (cr, cw), \
            ClientSession(cr, cw) as claude:
        await claude.initialize()
        names = {t.name for t in (await claude.list_tools()).tools}
        assert TOOLS <= names, f"missing tools: {TOOLS - names}"
        print(f"[claude] tools registered: {sorted(names)}")

        started = await call(claude, "relay_start", task="Smoke: design a cache",
                             first_agent="claude", thread_id=tid)
        print(f"[claude] relay_start -> thread={started['thread_id']} baton={started['baton']}")
        p1 = await call(claude, "relay_begin_turn", thread_id=tid)
        r1 = await call(claude, "relay_submit_turn", turn_token=p1["turn_token"],
                        body="Claude: LRU with a TTL.", next_baton="codex")
        print(f"[claude] submit -> turn={r1['turn_id']} created={r1['created']} baton->{r1['baton']}")

        async with stdio_client(params_for("codex", agents["codex"])) as (xr, xw), \
                ClientSession(xr, xw) as codex:
            await codex.initialize()
            p2 = await call(codex, "relay_begin_turn", thread_id=tid)
            prior = [e["author"] for e in p2["prior_events"]]
            print(f"[codex]  begin -> sees prior authors={prior} expected_id={p2['expected_last_turn_id']}")
            r2 = await call(codex, "relay_submit_turn", turn_token=p2["turn_token"],
                            body="Codex: bound it; evict on memory pressure.", next_baton="claude")
            print(f"[codex]  submit -> turn={r2['turn_id']} created={r2['created']} baton->{r2['baton']}")

        evs = await call(claude, "relay_events", thread_id=tid, since=0)
        authors = [e["author"] for e in evs]
        print(f"[claude] relay_events authors = {authors}")
        assert authors == ["claude", "codex"], authors  # exactly two, alternating
        state = await call(claude, "relay_status", thread_id=tid)
        # turn ids are global (autoincrement across threads), so check the relation, not 2:
        assert state["baton"] == "claude", state           # baton handed back
        assert state["last_turn_id"] == r2["turn_id"], state  # head == codex's turn
        print(f"\nPASS: two agents alternated over real stdio MCP. thread={tid} state={state}")


if __name__ == "__main__":
    asyncio.run(main())
