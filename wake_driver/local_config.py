"""Resolve machine-specific values without hardcoding personal paths in committed code.

Precedence per value: explicit env var -> gitignored ``data/local_config.json`` -> safe
default. This keeps the public tree free of absolute paths while letting a local install
bank its load-bearing values (the interpreter that has ``mcp``, the secrets location) in an
ignored file. ``.env.example`` documents the keys; ``data/`` is gitignored so the real file
never ships.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_LOCAL_CONFIG = REPO / "data" / "local_config.json"


def _local() -> dict[str, str]:
    """Load the gitignored local overrides, or an empty dict if absent/unreadable."""
    try:
        data = json.loads(_LOCAL_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolve(env_key: str, cfg_key: str, default: str) -> str:
    """First non-empty of: env var, local_config value, built-in default."""
    return os.environ.get(env_key) or _local().get(cfg_key) or default


def python_bin() -> str:
    """Interpreter used to spawn the relay MCP server; must have ``mcp`` installed."""
    return _resolve("WAKE_PYTHON_BIN", "python_bin", sys.executable)


def secrets_path() -> Path:
    """Path to the gitignored per-agent bearer-token store."""
    return Path(_resolve("WAKE_SECRETS_PATH", "secrets_path", str(REPO / "data" / "secrets.json")))
