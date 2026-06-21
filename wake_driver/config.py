"""Wake-driver config: where the router is, and which agent/thread this driver serves."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from router.config.credentials import load_tokens

_DEFAULTS = {
    "WAKE_BASE_URL": "http://127.0.0.1:8000",
    "WAKE_MAX_TURNS": "24",
    "WAKE_SPAWN_TIMEOUT": "600",
    "WAKE_LEASE_TTL": "3000",
}


@dataclass(frozen=True)
class Config:
    """All a driver needs to subscribe and drive one thread for one agent."""

    agent_id: str
    thread_id: str
    token: str
    base_url: str
    ws_url: str
    max_turn_cap: int
    spawn_timeout: int
    lease_ttl: int


def _get(env: dict[str, str], key: str) -> str:
    """Return an env value or its default (empty string if neither exists)."""
    return env.get(key, _DEFAULTS.get(key, ""))


def _ws_url(base_url: str) -> str:
    """Derive the ws(s) URL from the http(s) base URL."""
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://"):]
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://"):]
    raise ValueError(f"base_url must be http(s): {base_url!r}")


def load_config(env: dict[str, str], secrets_path: Path) -> Config:
    """Build a Config from env + secrets; fail fast on anything missing or incoherent."""
    agent_id = env.get("WAKE_AGENT_ID", "").strip()
    thread_id = env.get("WAKE_THREAD_ID", "").strip()
    if not agent_id or not thread_id:
        raise RuntimeError("WAKE_AGENT_ID and WAKE_THREAD_ID are required")
    token = load_tokens(secrets_path).agents.get(agent_id)
    if not token:
        raise RuntimeError(f"no bearer token for agent {agent_id!r} in {secrets_path}")
    base_url = _get(env, "WAKE_BASE_URL")
    spawn_timeout = int(_get(env, "WAKE_SPAWN_TIMEOUT"))
    lease_ttl = int(_get(env, "WAKE_LEASE_TTL"))
    if spawn_timeout >= lease_ttl:  # decision I: a turn must finish before its lease can expire
        raise RuntimeError(f"spawn_timeout ({spawn_timeout}) must be < lease_ttl ({lease_ttl})")
    return Config(agent_id, thread_id, token, base_url, _ws_url(base_url),
                  int(_get(env, "WAKE_MAX_TURNS")), spawn_timeout, lease_ttl)
