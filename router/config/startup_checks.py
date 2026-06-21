"""Startup safety checks: sync-root refusal, port availability, DB integrity."""
from __future__ import annotations

import os
import socket
import sqlite3
from pathlib import Path

from router.db.connection import quick_check

_SYNC_ENV_VARS = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
_SYNC_MARKERS = ("onedrive", "dropbox")


def _sync_roots() -> list[Path]:
    """Resolve known cloud-sync root paths from the environment."""
    roots: list[Path] = []
    for name in _SYNC_ENV_VARS:
        value = os.environ.get(name)
        if value:
            roots.append(Path(value).resolve())
    return roots


def _sync_marker(resolved: Path) -> str | None:
    """Return the offending sync root/name if resolved is under a sync location."""
    for root in _sync_roots():
        if root == resolved or root in resolved.parents:
            return str(root)
    lowered = [part.lower() for part in resolved.parts]
    for marker in _SYNC_MARKERS:
        if any(marker in part for part in lowered):
            return marker
    return None


def assert_not_synced(path: Path) -> None:
    """Refuse to run if path is under a OneDrive/Dropbox sync location."""
    resolved = path.resolve()
    marker = _sync_marker(resolved)
    if marker:
        raise RuntimeError(
            f"DB path {resolved} is under cloud-sync location '{marker}'; "
            "move the repo off the synced folder (SQLite corrupts there)."
        )


def assert_port_free(host: str, port: int) -> None:
    """Refuse to start if host:port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError as exc:
            raise RuntimeError(f"port {host}:{port} is already in use") from exc


def assert_db_intact(conn: sqlite3.Connection) -> None:
    """Raise if the database fails its integrity check."""
    result = quick_check(conn)
    if result != "ok":
        raise RuntimeError(f"router.db integrity check failed: {result}")
