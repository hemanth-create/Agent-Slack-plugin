"""Opaque turn token: pins lease_id + expected_last_turn_id + one idempotency key."""
from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from uuid import uuid4


@dataclass(frozen=True)
class TurnToken:
    thread_id: str
    lease_id: str
    expected_last_turn_id: int
    idempotency_key: str


def mint(thread_id: str, lease_id: str, expected_last_turn_id: int) -> TurnToken:
    """Create a token with one stable idempotency key for this whole turn."""
    key = f"{thread_id}:{expected_last_turn_id}:{uuid4().hex}"
    return TurnToken(thread_id, lease_id, expected_last_turn_id, key)


def encode(token: TurnToken) -> str:
    """Serialize to a base64url JSON string."""
    raw = json.dumps(asdict(token), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode(s: str) -> TurnToken:
    """Parse a token; raise ValueError on any malformed input."""
    try:
        data = json.loads(base64.urlsafe_b64decode(s.encode()))
        return TurnToken(
            data["thread_id"], data["lease_id"],
            int(data["expected_last_turn_id"]), data["idempotency_key"],
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"invalid turn token: {exc}") from exc
