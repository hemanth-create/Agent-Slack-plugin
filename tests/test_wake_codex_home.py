from __future__ import annotations

import tomllib
from pathlib import Path

import wake_driver.local_config as lc
from wake_driver.codex_home import codex_config_toml, write_codex_home


def test_codex_config_is_valid_toml_and_auto_approves_relay() -> None:
    raw = codex_config_toml("http://127.0.0.1:8000", "tok-123")
    cfg = tomllib.loads(raw)  # single-quoted Windows paths must parse (double quotes would not)
    relay = cfg["mcp_servers"]["relay"]
    assert relay["command"] == lc.python_bin()  # resolved interpreter, OS-agnostic
    assert relay["args"] == ["-m", "server.relay_mcp"]
    assert relay["default_tools_approval_mode"] == "approve"
    assert relay["env"]["RELAY_AGENT_ID"] == "codex"
    assert relay["env"]["RELAY_API_KEY"] == "tok-123"
    # every relay tool is individually auto-approved (codex denies untrusted tools under -a never)
    for tool in ("relay_begin_turn", "relay_submit_turn", "relay_halt_turn", "relay_status"):
        assert relay["tools"][tool]["approval_mode"] == "approve"


def test_write_codex_home_carries_auth_and_writes_config(tmp_path: Path) -> None:
    default_home = tmp_path / "default"
    default_home.mkdir()
    (default_home / "auth.json").write_text('{"token": "login"}', encoding="utf-8")
    home = Path(write_codex_home(tmp_path / "iso", "http://x:8000", "t", default_home))
    assert (home / "auth.json").read_text(encoding="utf-8") == '{"token": "login"}'
    assert "default_tools_approval_mode" in (home / "config.toml").read_text(encoding="utf-8")


def test_write_codex_home_tolerates_missing_auth(tmp_path: Path) -> None:
    home = Path(write_codex_home(tmp_path / "iso", "http://x:8000", "t", tmp_path / "nope"))
    assert (home / "config.toml").exists()
    assert not (home / "auth.json").exists()
