"""Submit an inbox draft to the local router's POST /turns endpoint."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def build_payload(args: argparse.Namespace, body: str) -> dict[str, Any]:
    """Build the TurnSubmission JSON body from CLI fields and draft text."""
    return {
        "thread_id": args.thread_id,
        "body": body,
        "reply_to": args.reply_to,
        "next_baton": args.next_baton,
        "idempotency_key": args.submission_id,
        "expected_last_turn_id": args.expected_last_turn_id,
        "processed_through_id": args.processed_through_id,
    }


def post_turn(
    api_url: str,
    token: str,
    payload: dict[str, Any],
    opener: Callable[..., Any] = urlopen,
) -> tuple[int, dict[str, Any]]:
    """POST the turn payload and return status plus parsed response JSON."""
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{api_url.rstrip('/')}/turns",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def _parser() -> argparse.ArgumentParser:
    """Return the submit-turn CLI parser."""
    parser = argparse.ArgumentParser(description="Submit a local agent draft to the router.")
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--next-baton", required=True)
    parser.add_argument("--submission-id", required=True)
    parser.add_argument("--expected-last-turn-id", required=True, type=int)
    parser.add_argument("--processed-through-id", required=True, type=int)
    parser.add_argument("--reply-to", type=int, default=None)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token-env", default="ROUTER_TOKEN")
    return parser


def main() -> int:
    """CLI entrypoint."""
    args = _parser().parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(f"missing token environment variable: {args.token_env}")
    body = args.draft.read_text(encoding="utf-8")
    status, response = post_turn(args.api_url, token, build_payload(args, body))
    print(json.dumps({"status": status, "response": response}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
