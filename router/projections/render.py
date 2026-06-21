"""Render thread.md and state.json projections from router.db data."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

from router.db import projections
from router.db.connection import connect


async def drain_dirty(
    db_path: Path, output_root: Path, writer_conn: sqlite3.Connection, writer_lock: asyncio.Lock
) -> int:
    """Drain dirty projections using a read snapshot and the single writer."""
    read_conn = connect(db_path, check_same_thread=False)
    try:
        return await _drain_dirty(read_conn, output_root, writer_conn, writer_lock)
    finally:
        read_conn.close()


async def _drain_dirty(
    read_conn: sqlite3.Connection,
    output_root: Path,
    writer_conn: sqlite3.Connection,
    writer_lock: asyncio.Lock,
) -> int:
    """Async drainer body split for tests and app wiring."""
    rendered = 0
    for thread_id in await asyncio.to_thread(projections.dirty_thread_ids, read_conn):
        data = await asyncio.to_thread(projections.load_projection_snapshot, read_conn, thread_id)
        if data is None:
            continue
        await asyncio.to_thread(_write_one, output_root, data)
        async with writer_lock:
            if await asyncio.to_thread(_clear_dirty, writer_conn, data):
                rendered += 1
    return rendered


def _write_one(output_root: Path, data: dict) -> None:
    """Write both projection files without mutating router.db."""
    thread = data["thread"]
    target = output_root / quote(thread["thread_id"], safe="")
    target.mkdir(parents=True, exist_ok=True)
    _replace_text(target / "thread.md", render_thread_md(data))
    _replace_text(target / "state.json", render_state_json(data))


def _clear_dirty(writer_conn: sqlite3.Connection, data: dict) -> bool:
    """Clear dirty through the writer connection if the rendered head is current."""
    thread = data["thread"]
    return projections.mark_rendered(
        writer_conn, thread["thread_id"], int(thread["last_turn_id"])
    )


def render_thread_md(data: dict) -> str:
    """Return a deterministic human-readable thread transcript."""
    thread = data["thread"]
    lines = [
        f"# Thread {thread['thread_id']}",
        "",
        f"status: {thread['status']}",
        f"baton: {thread['baton'] or ''}",
        f"last_turn_id: {thread['last_turn_id']}",
        "",
    ]
    for turn in data["turns"]:
        lines.extend(_turn_lines(turn))
    return "\n".join(lines).rstrip() + "\n"


def _turn_lines(turn: dict) -> list[str]:
    """Return the Markdown lines for one turn."""
    reply = "" if turn["reply_to"] is None else f" reply_to={turn['reply_to']}"
    return [
        f"## [{turn['author']}] #{turn['id']}{reply}",
        turn["body"],
        "",
    ]


def render_state_json(data: dict) -> str:
    """Return a deterministic machine-readable thread state projection."""
    thread = data["thread"]
    state = {
        "schema_version": 1,
        **thread,
        "participants": {
            item["agent"]: {"last_processed_id": item["last_processed_id"]}
            for item in data["participants"]
        },
    }
    return json.dumps(state, indent=2, sort_keys=True) + "\n"


def _replace_text(path: Path, text: str) -> None:
    """Atomically replace a text file using os.replace."""
    temp = path.with_name(f"{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
