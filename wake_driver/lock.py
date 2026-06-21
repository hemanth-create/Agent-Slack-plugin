"""Process-external single-flight: one in-flight drive per (thread, agent).

A Windows byte-range lock on a per-(thread,agent) file. It is held by the OS file
handle, so a driver crash releases it automatically -- no stale-lock cleanup needed.
"""
from __future__ import annotations

import msvcrt
from typing import IO


def acquire_singleflight(path: str) -> IO | None:
    """Take the lock; return the open handle, or None if another driver already holds it."""
    handle = open(path, "a+")  # noqa: SIM115 - handle is owned by the caller until release
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except OSError:
        handle.close()
        return None


def release_singleflight(handle: IO) -> None:
    """Release the lock and close the handle."""
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()
