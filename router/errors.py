"""Domain errors for the accept transaction: a code + an HTTP status."""
from __future__ import annotations


class AcceptError(Exception):
    """A rejected turn submission carrying a machine-readable code and HTTP status."""

    def __init__(self, code: str, http_status: int, detail: str | None = None) -> None:
        super().__init__(detail or code)
        self.code = code
        self.http_status = http_status
        self.detail = detail or code
