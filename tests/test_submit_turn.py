"""Tests for the local submit_turn script helpers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.submit_turn import build_payload, post_turn


class _Response:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")


def _args(tmp_path: Path) -> argparse.Namespace:
    draft = tmp_path / "draft.md"
    draft.write_text("hello", encoding="utf-8")
    return argparse.Namespace(
        draft=draft,
        thread_id="t1",
        next_baton="codex",
        submission_id="s1",
        expected_last_turn_id=0,
        processed_through_id=0,
        reply_to=None,
    )


def test_build_payload_uses_draft_body(tmp_path: Path) -> None:
    args = _args(tmp_path)
    payload = build_payload(args, args.draft.read_text(encoding="utf-8"))
    assert payload["body"] == "hello"
    assert payload["idempotency_key"] == "s1"


def test_post_turn_sends_authorization_header_only() -> None:
    captured: dict[str, Any] = {}

    def opener(request: Any, timeout: int) -> _Response:
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        captured["auth"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response(201, {"id": 1})

    status, body = post_turn("http://router", "secret-token", {"thread_id": "t1"}, opener)
    assert status == 201 and body["id"] == 1
    assert captured["url"] == "http://router/turns"
    assert captured["auth"] == "Bearer secret-token"
    assert "secret-token" not in json.dumps(captured["body"])
