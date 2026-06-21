"""Best-effort projection draining for committed API writes."""
from __future__ import annotations

import logging

from fastapi import Request

from router.projections.render import drain_dirty

_LOG = logging.getLogger(__name__)


async def drain_projections_best_effort(request: Request) -> None:
    """Render dirty projections after commit without failing committed writes."""
    try:
        await drain_dirty(
            request.app.state.db_path,
            request.app.state.projections_path,
            request.app.state.writer,
            request.app.state.writer_lock,
        )
    except Exception:
        _LOG.exception("projection drain failed after committed write")
