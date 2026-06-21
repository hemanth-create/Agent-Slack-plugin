"""Generate the --mcp-config a spawned Claude uses to load ONLY the relay server.

Resolved interpreter (a venv that has `mcp`, via ``local_config.python_bin``) and absolute
cwd (the plugin dir holding server/relay_mcp.py), because ${CLAUDE_PLUGIN_ROOT} is not
interpolated when the config is passed via --mcp-config. RELAY_API_KEY is NOT written here --
the driver passes it through the spawn's host env so the token never lands in a file.
"""
from __future__ import annotations

import json
from pathlib import Path

from wake_driver.local_config import python_bin

PLUGIN_ROOT = str(Path(__file__).resolve().parents[1] / "plugins" / "agent-relay")


def relay_mcp_config(agent_id: str, base_url: str, allowed: str = "claude,codex") -> dict:
    """Build the mcpServers dict for the relay server (token comes from host env)."""
    return {
        "mcpServers": {
            "relay": {
                "command": python_bin(),
                "args": ["-m", "server.relay_mcp"],
                "cwd": PLUGIN_ROOT,
                "env": {
                    "RELAY_BASE_URL": base_url,
                    "RELAY_AGENT_ID": agent_id,
                    "RELAY_ALLOWED_AGENTS": allowed,
                    # Claude does NOT apply the config `cwd` when launching the server
                    # (verified in the Phase-0.4 smoke), so make `-m server.relay_mcp`
                    # resolve regardless of cwd. RELAY_API_KEY stays in the host env.
                    "PYTHONPATH": PLUGIN_ROOT,
                },
            }
        }
    }


def write_relay_mcp_config(path: Path, agent_id: str, base_url: str) -> Path:
    """Write the relay --mcp-config JSON to `path` and return it."""
    path.write_text(
        json.dumps(relay_mcp_config(agent_id, base_url), indent=2), encoding="utf-8"
    )
    return path
