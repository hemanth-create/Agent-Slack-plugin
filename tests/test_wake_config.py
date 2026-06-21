from __future__ import annotations

from pathlib import Path

import pytest

from router.config.credentials import AgentTokens, write_tokens
from wake_driver.config import load_config
from wake_driver.ws_listen import connect_args


def _secrets(tmp_path: Path) -> Path:
    p = tmp_path / "secrets.json"
    write_tokens(p, AgentTokens(agents={"claude": "c" * 40, "codex": "x" * 40}))
    return p


def _env(**over: str) -> dict[str, str]:
    base = {"WAKE_AGENT_ID": "claude", "WAKE_THREAD_ID": "t1"}
    base.update(over)
    return base


def test_load_config_happy_path(tmp_path: Path) -> None:
    cfg = load_config(_env(), _secrets(tmp_path))
    assert cfg.agent_id == "claude" and cfg.thread_id == "t1"
    assert cfg.token == "c" * 40
    assert cfg.base_url == "http://127.0.0.1:8000"
    assert cfg.ws_url == "ws://127.0.0.1:8000"
    assert (cfg.max_turn_cap, cfg.spawn_timeout, cfg.lease_ttl) == (24, 600, 3000)


def test_missing_agent_or_thread_fails(tmp_path: Path) -> None:
    s = _secrets(tmp_path)
    with pytest.raises(RuntimeError):
        load_config(_env(WAKE_AGENT_ID=""), s)
    with pytest.raises(RuntimeError):
        load_config(_env(WAKE_THREAD_ID=""), s)


def test_unknown_agent_token_fails(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no bearer token"):
        load_config(_env(WAKE_AGENT_ID="ghost"), _secrets(tmp_path))


def test_spawn_timeout_must_be_under_lease_ttl(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="must be <"):
        load_config(_env(WAKE_SPAWN_TIMEOUT="3000", WAKE_LEASE_TTL="3000"), _secrets(tmp_path))


def test_ws_url_https_maps_to_wss(tmp_path: Path) -> None:
    cfg = load_config(_env(WAKE_BASE_URL="https://host:9"), _secrets(tmp_path))
    assert cfg.ws_url == "wss://host:9"


def test_connect_args_sets_loopback_origin_and_bearer() -> None:
    uri, headers = connect_args("ws://127.0.0.1:8000", "t1", "tok")
    assert uri == "ws://127.0.0.1:8000/ws?thread_id=t1"
    assert headers["Authorization"] == "Bearer tok"
    assert headers["Origin"] == "http://127.0.0.1"
