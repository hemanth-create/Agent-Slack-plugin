"""Tests for router.auth: token resolution, HTTP dependency, WS origin guard."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from router.auth import (
    authenticate,
    install_tokens,
    known_agents,
    origin_allowed,
    resolve_agent,
    verify_ws,
)

_MAP = {"tok-claude": "claude", "tok-codex": "codex"}


def test_resolve_agent_matches() -> None:
    assert resolve_agent("tok-codex", _MAP) == "codex"


def test_resolve_agent_rejects_unknown() -> None:
    assert resolve_agent("nope", _MAP) is None


def test_authenticate_returns_agent() -> None:
    install_tokens(_MAP)
    assert authenticate("Bearer tok-claude") == "claude"


def test_known_agents_exposes_agents_not_tokens() -> None:
    install_tokens(_MAP)
    assert known_agents() == frozenset({"claude", "codex"})
    assert "tok-claude" not in known_agents()


def test_authenticate_rejects_missing() -> None:
    install_tokens(_MAP)
    with pytest.raises(HTTPException) as exc:
        authenticate(None)
    assert exc.value.status_code == 401


def test_authenticate_rejects_bad_token() -> None:
    install_tokens(_MAP)
    with pytest.raises(HTTPException) as exc:
        authenticate("Bearer wrong")
    assert exc.value.status_code == 401


def test_authenticate_rejects_empty_bearer() -> None:
    install_tokens(_MAP)
    with pytest.raises(HTTPException) as exc:
        authenticate("Bearer ")
    assert exc.value.status_code == 401


def test_origin_allows_localhost() -> None:
    assert origin_allowed("http://localhost:8765")
    assert origin_allowed("http://127.0.0.1:5173")


def test_origin_rejects_missing() -> None:
    assert not origin_allowed(None)


def test_origin_rejects_remote() -> None:
    assert not origin_allowed("https://evil.example.com")


def test_origin_rejects_nonhttp_scheme() -> None:
    assert not origin_allowed("ftp://localhost:21")
    assert not origin_allowed("file://localhost/x")


def test_verify_ws_rejects_bad_origin() -> None:
    install_tokens(_MAP)
    with pytest.raises(HTTPException) as exc:
        verify_ws("Bearer tok-claude", "https://evil.example.com")
    assert exc.value.status_code == 403


def test_verify_ws_rejects_missing_origin() -> None:
    install_tokens(_MAP)
    with pytest.raises(HTTPException) as exc:
        verify_ws("Bearer tok-claude", None)
    assert exc.value.status_code == 403


def test_verify_ws_accepts_local() -> None:
    install_tokens(_MAP)
    assert verify_ws("Bearer tok-codex", "http://localhost:8765") == "codex"
