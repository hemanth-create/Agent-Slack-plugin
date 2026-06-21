from __future__ import annotations

import json as jsonlib

import httpx
import pytest

from server.router_api import RouterApi, RouterError

_LEASE = {
    "lease_id": "L", "thread_id": "t1", "agent": "claude",
    "acquired_at": "a", "expires_at": "e", "heartbeat_at": None, "status": "active",
}


def make_api(handler, agent="claude"):
    """A RouterApi whose AsyncClient is wired to an in-memory mock transport."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test",
        headers={"Authorization": "Bearer tok-123"},
    )
    return RouterApi(client, agent, frozenset({"claude", "codex"}), 3000)


async def test_post_turn_sends_six_fields_with_bearer_and_reports_created() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = jsonlib.loads(request.content)
        return httpx.Response(201, json={
            "id": 5, "thread_id": "t1", "author": "claude",
            "reply_to": None, "ts": "now", "body": "hi",
        })

    api = make_api(handler)
    created, turn = await api.post_turn("t1", "hi", "codex", "t1:0:k", 0, 0)
    assert created is True
    assert turn["id"] == 5
    assert seen["path"] == "/turns"
    assert seen["auth"] == "Bearer tok-123"
    assert set(seen["body"]) == {
        "thread_id", "body", "next_baton", "idempotency_key",
        "expected_last_turn_id", "processed_through_id",
    }
    await api._client.aclose()


async def test_post_turn_replay_is_not_created() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": 5, "thread_id": "t1", "author": "claude",
            "reply_to": None, "ts": "now", "body": "hi",
        })

    api = make_api(handler)
    created, _ = await api.post_turn("t1", "hi", "codex", "t1:0:k", 0, 0)
    assert created is False
    await api._client.aclose()


async def test_acquire_lease_uses_ttl_seconds_key() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = jsonlib.loads(request.content)
        return httpx.Response(201, json=_LEASE)

    api = make_api(handler)
    lease = await api.acquire_lease("t1", 3000)
    assert seen["body"] == {"thread_id": "t1", "ttl_seconds": 3000}
    assert lease["lease_id"] == "L"
    await api._client.aclose()


async def test_get_events_passes_thread_id_and_since_query() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    api = make_api(handler)
    await api.get_events("t1", 2)
    assert seen["params"]["thread_id"] == "t1"
    assert seen["params"]["since"] == "2"
    await api._client.aclose()


async def test_raise_surfaces_router_error_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"error": "stale_read", "detail": "x"})

    api = make_api(handler)
    with pytest.raises(RouterError) as ei:
        await api.get_thread("t1")
    assert "stale_read" in str(ei.value)
    await api._client.aclose()


async def test_release_best_effort_swallows_lease_not_active() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"error": "lease_not_active", "detail": "x"})

    api = make_api(handler)
    assert await api.release_best_effort("t1", "L") is False
    await api._client.aclose()


async def test_release_best_effort_reraises_other_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"error": "lease_conflict", "detail": "x"})

    api = make_api(handler)
    with pytest.raises(RouterError):
        await api.release_best_effort("t1", "L")
    await api._client.aclose()


async def test_release_best_effort_success_returns_true() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_LEASE)

    api = make_api(handler)
    assert await api.release_best_effort("t1", "L") is True
    await api._client.aclose()


async def test_halt_turn_posts_to_turns_halt_with_self_baton() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = jsonlib.loads(request.content)
        return httpx.Response(200, json={
            "id": 7, "thread_id": "t1", "author": "claude",
            "reply_to": None, "ts": "now", "body": "stuck",
        })

    api = make_api(handler)
    turn = await api.halt_turn("t1", "stuck", "k1", 0, 0, "needs_human", "recovery_required")
    assert seen["path"] == "/turns/halt"
    assert seen["body"]["next_baton"] == "claude"  # baton stays with the halter
    assert seen["body"]["status"] == "needs_human"
    assert seen["body"]["status_reason"] == "recovery_required"
    assert turn["id"] == 7
    await api._client.aclose()


async def test_resume_turn_posts_to_turns_resume() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = jsonlib.loads(request.content)
        return httpx.Response(200, json={
            "id": 8, "thread_id": "t1", "author": "codex",
            "reply_to": None, "ts": "now", "body": "answer",
        })

    api = make_api(handler)
    turn = await api.resume_turn("t1", "answer", "claude", "r1", 7, 7)
    assert seen["path"] == "/turns/resume"
    assert seen["body"]["next_baton"] == "claude"
    assert turn["id"] == 8
    await api._client.aclose()


async def test_from_env_sets_bearer_header() -> None:
    api = RouterApi.from_env("http://x", "tok", "claude", ("claude", "codex"), 3000)
    assert api._client.headers["authorization"] == "Bearer tok"
    assert api.agent_id == "claude"
    await api._client.aclose()
