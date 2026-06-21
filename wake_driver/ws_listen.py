"""Subscribe to the router /ws and yield WakeEvent frames.

The router rejects a missing/non-loopback Origin (auth.verify_ws), and Python WS
clients do not send one by default, so we set Origin + Bearer explicitly. Reconnect
and de-dup are the caller's job (the driver seeds last_processed from relay_status).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from websockets.asyncio.client import connect

_ORIGIN = "http://127.0.0.1"


def connect_args(ws_url: str, thread_id: str, token: str) -> tuple[str, dict[str, str]]:
    """Build the (uri, headers) for one /ws subscription (Origin + Bearer required)."""
    uri = f"{ws_url}/ws?thread_id={thread_id}"
    headers = {"Authorization": f"Bearer {token}", "Origin": _ORIGIN}
    return uri, headers


async def wake_stream(ws_url: str, thread_id: str, token: str) -> AsyncIterator[dict]:
    """Yield WakeEvent dicts from a single /ws connection (closes when the socket does)."""
    uri, headers = connect_args(ws_url, thread_id, token)
    async with connect(uri, additional_headers=headers) as ws:
        async for frame in ws:
            yield json.loads(frame)
