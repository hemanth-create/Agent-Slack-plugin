"""Bearer-token auth: resolve tokens to agents; guard HTTP and WS handshakes."""
from __future__ import annotations

import hmac
from urllib.parse import urlsplit

from fastapi import Header, HTTPException, status

_BEARER_PREFIX = "Bearer "
_LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})

# token -> agent_id, installed once at startup from data/secrets.json.
_token_map: dict[str, str] = {}


def install_tokens(token_map: dict[str, str]) -> None:
    """Register the token -> agent map (called once at app startup)."""
    _token_map.clear()
    _token_map.update(token_map)


def known_agents() -> frozenset[str]:
    """Return installed agent ids without exposing their tokens."""
    return frozenset(_token_map.values())


def resolve_agent(token: str, token_map: dict[str, str]) -> str | None:
    """Return the agent for an exact (constant-time) token match, else None."""
    for known, agent in token_map.items():
        if hmac.compare_digest(token, known):
            return agent
    return None


def _bearer_token(authorization: str | None) -> str:
    """Extract the raw token from an 'Authorization: Bearer ...' header or 401."""
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization[len(_BEARER_PREFIX):]
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "empty bearer token")
    return token


def authenticate(authorization: str | None) -> str:
    """Resolve an Authorization header to an agent id, or raise 401."""
    agent = resolve_agent(_bearer_token(authorization), _token_map)
    if agent is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")
    return agent


async def verify_api_key(authorization: str | None = Header(default=None)) -> str:
    """FastAPI HTTP dependency: return the authenticated agent id."""
    return authenticate(authorization)


def origin_allowed(origin: str | None) -> bool:
    """Allow a present http(s) Origin with a loopback host only; missing is rejected.

    Strict v0 rule: clients (incl. the VS Code Node ws client) must set an Origin;
    'missing means OK' would leave a silent bypass on the WS security boundary.
    """
    if origin is None:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in ("http", "https") and parsed.hostname in _LOCAL_HOSTNAMES


def verify_ws(authorization: str | None, origin: str | None) -> str:
    """WS handshake guard: require a loopback Origin, then bearer auth."""
    if not origin_allowed(origin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "origin not allowed")
    return authenticate(authorization)
