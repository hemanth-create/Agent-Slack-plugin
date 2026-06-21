"""Tests for generated thread.md/state.json projections."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from router.db.connection import connect
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH
from router.projections import render as render_module
from router.projections.render import drain_dirty


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "router.db", SCHEMA_PATH)
    conn.execute(
        "INSERT INTO threads(thread_id, status, baton, workspace_id, created_at) "
        "VALUES('t/1','active','codex','ws','now')"
    )
    cur = conn.execute(
        "INSERT INTO turns(thread_id, author, ts, body, payload_hash) "
        "VALUES('t/1','claude','now','hello','h')"
    )
    conn.execute("UPDATE threads SET last_turn_id=? WHERE thread_id='t/1'", (cur.lastrowid,))
    conn.execute(
        "INSERT INTO participants(thread_id, agent, last_processed_id) VALUES('t/1','claude',?)",
        (cur.lastrowid,),
    )
    conn.execute(
        "INSERT INTO projections_dirty(thread_id, dirty, last_rendered_turn_id) VALUES('t/1',1,0)"
    )
    return conn


def test_drain_dirty_writes_thread_and_state(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    conn.close()
    writer = connect(tmp_path / "router.db", check_same_thread=False)
    try:
        assert asyncio.run(
            drain_dirty(tmp_path / "router.db", tmp_path / "out", writer, asyncio.Lock())
        ) == 1
        dirty = writer.execute(
            "SELECT dirty FROM projections_dirty WHERE thread_id='t/1'"
        ).fetchone()
    finally:
        writer.close()
    thread_md = (tmp_path / "out" / "t%2F1" / "thread.md").read_text(encoding="utf-8")
    state = json.loads((tmp_path / "out" / "t%2F1" / "state.json").read_text(encoding="utf-8"))
    assert "## [claude] #1" in thread_md
    assert state["thread_id"] == "t/1"
    assert dirty["dirty"] == 0


def test_render_failure_leaves_dirty_set(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    conn.close()
    writer = connect(tmp_path / "router.db", check_same_thread=False)
    blocked_root = tmp_path / "out"
    blocked_root.write_text("not a directory", encoding="utf-8")
    try:
        with pytest.raises(OSError):
            asyncio.run(
                drain_dirty(tmp_path / "router.db", blocked_root, writer, asyncio.Lock())
            )
        dirty = writer.execute(
            "SELECT dirty FROM projections_dirty WHERE thread_id='t/1'"
        ).fetchone()
    finally:
        writer.close()
    assert dirty["dirty"] == 1


def test_drain_dirty_keeps_dirty_when_head_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = _db(tmp_path)
    conn.close()
    writer = connect(tmp_path / "router.db", check_same_thread=False)
    original = render_module._replace_text
    moved = False

    def replace_and_move_head(path: Path, text: str) -> None:
        nonlocal moved
        original(path, text)
        if not moved and path.name == "thread.md":
            cur = writer.execute(
                "INSERT INTO turns(thread_id, author, ts, body, payload_hash) "
                "VALUES('t/1','codex','later','new head','h2')"
            )
            writer.execute(
                "UPDATE threads SET last_turn_id=? WHERE thread_id='t/1'",
                (cur.lastrowid,),
            )
            moved = True

    monkeypatch.setattr(render_module, "_replace_text", replace_and_move_head)
    try:
        assert asyncio.run(
            drain_dirty(tmp_path / "router.db", tmp_path / "out", writer, asyncio.Lock())
        ) == 0
        dirty = writer.execute(
            "SELECT dirty, last_rendered_turn_id FROM projections_dirty WHERE thread_id='t/1'"
        ).fetchone()
    finally:
        writer.close()
    assert dirty["dirty"] == 1
    assert dirty["last_rendered_turn_id"] == 0


def test_drain_dirty_clears_through_writer_connection(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    conn.close()
    writer = connect(tmp_path / "router.db", check_same_thread=False)
    try:
        count = asyncio.run(
            drain_dirty(tmp_path / "router.db", tmp_path / "out", writer, asyncio.Lock())
        )
        dirty = writer.execute(
            "SELECT dirty FROM projections_dirty WHERE thread_id='t/1'"
        ).fetchone()
    finally:
        writer.close()
    assert count == 1
    assert dirty["dirty"] == 0
