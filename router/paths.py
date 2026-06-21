"""Filesystem paths for the router: repo root, data dir, and DB locations."""
from __future__ import annotations

from pathlib import Path

# This file is <repo>/router/paths.py, so parents[1] is the repo root.
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
DATA_DIR: Path = REPO_ROOT / "data"
DB_PATH: Path = DATA_DIR / "router.db"
SECRETS_PATH: Path = DATA_DIR / "secrets.json"
PROJECTIONS_PATH: Path = DATA_DIR / "projections"
SCHEMA_PATH: Path = REPO_ROOT / "router" / "db" / "schema.sql"


def ensure_data_dir() -> Path:
    """Create the gitignored data dir if missing and return it."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
