"""Canonical payload hashing for idempotency (server-computed, never client-sent)."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def payload_hash(fields: dict[str, Any]) -> str:
    """Stable SHA-256 over the sorted-key JSON of the canonical submission fields."""
    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
