"""Stdio MCP server exposing the five relay tools. Never print to stdout (JSON-RPC).

Config comes from env; the bearer token (RELAY_API_KEY) is required and read here so a
misconfigured server fails fast at startup rather than mid-collaboration.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from server import relay_ops
from server.relay_models import Event, NextTurn, SubmitResult, ThreadState, TurnPrompt
from server.router_api import RouterApi

mcp = FastMCP("agent-relay")
_API: RouterApi | None = None


def build_api() -> RouterApi:
    """Build the router client from env; fail fast if the bearer token is missing."""
    token = os.environ.get("RELAY_API_KEY")
    if not token:
        raise RuntimeError("RELAY_API_KEY is required (this agent's router bearer token)")
    allowed = [a for a in os.environ.get("RELAY_ALLOWED_AGENTS", "claude,codex").split(",") if a]
    return RouterApi.from_env(
        os.environ.get("RELAY_BASE_URL", "http://127.0.0.1:8000"),
        token,
        os.environ.get("RELAY_AGENT_ID", "claude"),
        allowed,
        int(os.environ.get("RELAY_LEASE_TTL_SECONDS", "3000")),
    )


def _api() -> RouterApi:
    if _API is None:  # pragma: no cover - main() sets this before mcp.run()
        raise RuntimeError("relay server not initialized")
    return _API


@mcp.tool()
async def relay_start(task: str, first_agent: str = "claude",
                      thread_id: str | None = None, workspace_id: str = "ws") -> NextTurn:
    """Open a collaboration thread; the first agent addresses `task` in its first turn."""
    return await relay_ops.start(_api(), task, first_agent, thread_id, workspace_id)


@mcp.tool()
async def relay_begin_turn(thread_id: str) -> TurnPrompt:
    """Claim your turn: verify the baton is yours, take a lease, and read the thread."""
    return await relay_ops.begin_turn(_api(), thread_id)


@mcp.tool()
async def relay_submit_turn(turn_token: str, body: str, next_baton: str,
                            status: str = "continue",
                            question: str | None = None) -> SubmitResult:
    """Record your turn and hand the baton to `next_baton`. Halts go in the body text."""
    return await relay_ops.submit_turn(_api(), turn_token, body, next_baton, status, question)


@mcp.tool()
async def relay_halt_turn(turn_token: str, body: str, status: str = "needs_human",
                          question: str | None = None) -> SubmitResult:
    """Halt for a human: record your turn AND set needs_human/blocked atomically (keep the baton)."""
    return await relay_ops.halt_turn(_api(), turn_token, body, status, question)


@mcp.tool()
async def relay_status(thread_id: str) -> ThreadState:
    """Read a thread's routing state: status, baton, and last turn id."""
    return await relay_ops.status(_api(), thread_id)


@mcp.tool()
async def relay_events(thread_id: str, since: int = 0) -> list[Event]:
    """List the thread's turns after `since` (0 = from the start)."""
    return await relay_ops.events(_api(), thread_id, since)


def main() -> None:
    """Initialize the router client (fail-fast) and serve the tools over stdio."""
    global _API
    _API = build_api()
    mcp.run()


if __name__ == "__main__":
    main()
