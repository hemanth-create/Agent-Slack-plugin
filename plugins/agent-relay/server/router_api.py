"""Thin async HTTP client of the FastAPI router. Holds one agent's bearer token.

Every method maps to a shipped router route; no DB or `router.*` imports. `created`
lives only in the HTTP status (201 vs 200), so post_turn returns it explicitly.
"""
from __future__ import annotations

import httpx


class RouterError(RuntimeError):
    """A structured router error surfaced to the agent (carries the router code)."""


class RouterApi:
    """One agent's view of the router: authenticated, single base URL."""

    def __init__(self, client: httpx.AsyncClient, agent_id, allowed, lease_ttl) -> None:
        self._client = client
        self.agent_id = agent_id
        self.allowed = frozenset(allowed)
        self.lease_ttl = lease_ttl

    @classmethod
    def from_env(cls, base_url, token, agent_id, allowed, lease_ttl) -> "RouterApi":
        """Build a client that sends `Authorization: Bearer <token>` on every call."""
        client = httpx.AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {token}"}
        )
        return cls(client, agent_id, allowed, lease_ttl)

    def _raise(self, resp: httpx.Response) -> None:
        """Turn a non-2xx response into a RouterError carrying the router's code."""
        if resp.is_success:
            return
        code = "http_error"
        try:
            code = resp.json().get("error", code)  # errors.py -> {"error": ...}
        except Exception:
            pass
        raise RouterError(f"{code} (HTTP {resp.status_code})")

    async def create_thread(self, thread_id, workspace_id, initial_baton) -> dict:
        resp = await self._client.post("/threads", json={
            "thread_id": thread_id, "workspace_id": workspace_id,
            "initial_baton": initial_baton,
        })
        self._raise(resp)
        return resp.json()

    async def get_thread(self, thread_id) -> dict:
        resp = await self._client.get(f"/threads/{thread_id}")
        self._raise(resp)
        return resp.json()

    async def get_events(self, thread_id, since=0) -> list[dict]:
        resp = await self._client.get(
            "/events", params={"thread_id": thread_id, "since": since}
        )
        self._raise(resp)
        return resp.json()

    async def acquire_lease(self, thread_id, ttl_seconds) -> dict:
        resp = await self._client.post(
            "/leases/acquire", json={"thread_id": thread_id, "ttl_seconds": ttl_seconds}
        )
        self._raise(resp)
        return resp.json()

    async def post_turn(self, thread_id, body, next_baton, idempotency_key,
                        expected_last_turn_id, processed_through_id) -> tuple[bool, dict]:
        resp = await self._client.post("/turns", json={  # reply_to omitted -> None
            "thread_id": thread_id, "body": body, "next_baton": next_baton,
            "idempotency_key": idempotency_key,
            "expected_last_turn_id": expected_last_turn_id,
            "processed_through_id": processed_through_id,
        })
        self._raise(resp)
        return resp.status_code == 201, resp.json()  # created lives only in the status

    async def halt_turn(self, thread_id, body, idempotency_key, expected_last_turn_id,
                        processed_through_id, status, status_reason) -> dict:
        """Record a halting turn that atomically flips the thread off 'active' (baton kept)."""
        resp = await self._client.post("/turns/halt", json={
            "thread_id": thread_id, "body": body, "next_baton": self.agent_id,
            "idempotency_key": idempotency_key,
            "expected_last_turn_id": expected_last_turn_id,
            "processed_through_id": processed_through_id,
            "status": status, "status_reason": status_reason,
        })
        self._raise(resp)
        return resp.json()

    async def resume_turn(self, thread_id, body, next_baton, idempotency_key,
                          expected_last_turn_id, processed_through_id) -> dict:
        """Operator: append an answer and reactivate a halted thread (wakes next_baton)."""
        resp = await self._client.post("/turns/resume", json={
            "thread_id": thread_id, "body": body, "next_baton": next_baton,
            "idempotency_key": idempotency_key,
            "expected_last_turn_id": expected_last_turn_id,
            "processed_through_id": processed_through_id,
        })
        self._raise(resp)
        return resp.json()

    async def release_best_effort(self, thread_id, lease_id) -> bool:
        """Release a lease; swallow `lease_not_active` (idempotent replay already freed it)."""
        try:
            resp = await self._client.post(
                "/leases/release", json={"thread_id": thread_id, "lease_id": lease_id}
            )
            self._raise(resp)
            return True
        except RouterError as exc:
            if "lease_not_active" in str(exc):
                return False
            raise

    async def aclose(self) -> None:
        await self._client.aclose()
