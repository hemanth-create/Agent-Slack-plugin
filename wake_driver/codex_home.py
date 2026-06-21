"""Build an isolated CODEX_HOME for the codex driver: login carried over, relay auto-approved.

Three things the Phase-0.4 codex smoke proved necessary:
  1. Codex denies un-trusted MCP calls under `-a never` ("user cancelled MCP tool call"),
     so the relay tools are marked approval_mode="approve" (NOT a dangerous bypass; shell
     commands stay sandboxed).
  2. Windows paths must be single-quoted TOML literals -- double quotes treat `\\` as escapes.
  3. Auth lives in CODEX_HOME, so auth.json is carried over or codex 401s.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from wake_driver.local_config import python_bin
from wake_driver.relay_config import PLUGIN_ROOT

_TOOLS = ("relay_start", "relay_begin_turn", "relay_submit_turn",
          "relay_halt_turn", "relay_status", "relay_events")


def codex_config_toml(base_url: str, token: str) -> str:
    """Render the codex config.toml that registers AND auto-approves the relay MCP server."""
    py = python_bin()
    env = (f'{{ RELAY_BASE_URL = "{base_url}", RELAY_AGENT_ID = "codex", '
           f'RELAY_ALLOWED_AGENTS = "claude,codex", RELAY_API_KEY = "{token}", '
           f"PYTHONPATH = '{PLUGIN_ROOT}' }}")
    body = (f"[mcp_servers.relay]\ncommand = '{py}'\nargs = [\"-m\", \"server.relay_mcp\"]\n"
            f"cwd = '{PLUGIN_ROOT}'\ntool_timeout_sec = 120\n"
            f'default_tools_approval_mode = "approve"\nenv = {env}\n')
    for tool in _TOOLS:
        body += f'\n[mcp_servers.relay.tools.{tool}]\napproval_mode = "approve"\n'
    return body


def write_codex_home(home: Path, base_url: str, token: str, default_home: Path) -> str:
    """Create the isolated CODEX_HOME (carry auth.json + the relay config); return its path."""
    home.mkdir(parents=True, exist_ok=True)
    auth = default_home / "auth.json"
    if auth.exists():
        shutil.copy2(auth, home / "auth.json")  # carry codex's login or it 401s
    (home / "config.toml").write_text(codex_config_toml(base_url, token), encoding="utf-8")
    return str(home)
