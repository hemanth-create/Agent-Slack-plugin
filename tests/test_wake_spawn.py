from __future__ import annotations

import json
from pathlib import Path

from wake_driver.relay_config import relay_mcp_config, write_relay_mcp_config
from wake_driver.spawn import claude_argv, codex_argv, prompt_for


def test_claude_argv_auto_approves_relay_and_omits_bare() -> None:
    argv = claude_argv("claude", "relay.json", max_turns=6)
    assert "-p" in argv and "--bare" not in argv
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert argv[argv.index("--allowedTools") + 1] == "mcp__relay__*"
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--mcp-config") + 1] == "relay.json"
    assert argv[argv.index("--max-turns") + 1] == "6"


def test_codex_argv_puts_a_never_before_exec() -> None:
    argv = codex_argv("codex", "C:/clone", "out.txt")
    assert argv.index("-a") < argv.index("exec")          # verified flag order on 0.141.0
    assert argv[argv.index("-a") + 1] == "never"
    assert "--json" in argv and "--skip-git-repo-check" in argv
    assert argv[argv.index("-C") + 1] == "C:/clone"
    assert argv[argv.index("-o") + 1] == "out.txt"
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"


def test_prompt_names_thread_other_and_forbids_self_baton() -> None:
    p = prompt_for("t1", "codex")
    assert "t1" in p and 'next_baton="codex"' in p
    assert "NEVER set next_baton to yourself" in p
    assert "relay_halt_turn" in p and "EXACTLY ONE turn" in p


def test_relay_mcp_config_absolute_interpreter_and_no_token() -> None:
    relay = relay_mcp_config("claude", "http://127.0.0.1:8000")["mcpServers"]["relay"]
    assert relay["command"].endswith("python.exe")
    assert relay["args"] == ["-m", "server.relay_mcp"]
    assert relay["cwd"].replace("\\", "/").endswith("plugins/agent-relay")
    assert relay["env"]["RELAY_AGENT_ID"] == "claude"
    assert relay["env"]["PYTHONPATH"].replace("\\", "/").endswith("plugins/agent-relay")
    assert "RELAY_API_KEY" not in relay["env"]            # token stays in host env, never a file


def test_write_relay_mcp_config_roundtrips(tmp_path: Path) -> None:
    p = write_relay_mcp_config(tmp_path / "relay.json", "codex", "http://x:8000")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mcpServers"]["relay"]["env"]["RELAY_AGENT_ID"] == "codex"
