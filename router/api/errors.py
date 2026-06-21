"""FastAPI handler translating AcceptError into a structured JSON body."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from router.errors import AcceptError


async def accept_error_handler(_request: Request, exc: AcceptError) -> JSONResponse:
    """Render an AcceptError as {error, detail} with its HTTP status."""
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": exc.code, "detail": exc.detail},
    )
