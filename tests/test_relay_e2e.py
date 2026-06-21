"""In-process proof: two relay agents alternate turns against the REAL router app.

ASGITransport does not run the app lifespan, so the fixture replicates it (tokens,
writer, projections, a writer_lock bound to THIS event loop). No TestClient wrapper:
its portal loop would bind the Lock to a different loop than pytest-asyncio's.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio

from router.api.app import app
from router.auth import install_tokens
from router.config.credentials import AgentTokens, reverse_map
from router.db.connection import connect
from router.db.init_db import init_db
from router.paths import SCHEMA_PATH
from server import relay_ops
from server.router_api import RouterApi

TOK = {"claude": "c" * 40, "codex": "x" * 40}


@pytest_asyncio.fixture
async def agents(tmp_path, monkeypatch):
    db = tmp_path / "router.db"
    init_db(db, SCHEMA_PATH).close()
    (tmp_path / "projections").mkdir()
    install_tokens(reverse_map(AgentTokens(agents=TOK)))  # lifespan normally does this
    monkeypatch.setattr("router.api.app.DB_PATH", db)     # reads use the module global
    # Replicate lifespan IN THIS event loop:
    app.state.db_path = db
    app.state.projections_path = tmp_path / "projections"
    app.state.writer = connect(db, check_same_thread=False)
    app.state.writer_lock = asyncio.Lock()
    transport = httpx.ASGITransport(app=app)

    def mk(agent: str) -> RouterApi:
        client = httpx.AsyncClient(transport=transport, base_url="http://test",
                                   headers={"Authorization": f"Bearer {TOK[agent]}"})
        return RouterApi(client, agent, frozenset(TOK), 3000)

    claude, codex = mk("claude"), mk("codex")
    try:
        yield claude, codex
    finally:
        await claude.aclose()
        await codex.aclose()
        app.state.writer.close()


async def test_two_agents_alternate_turns_through_the_router(agents) -> None:
    claude, codex = agents

    # 1. start: thread created, baton on the first agent
    started = await relay_ops.start(claude, "Design the cache", first_agent="claude",
                                    thread_id="t1")
    assert started.baton == "claude"
    assert started.last_turn_id == 0

    # 2. claude begins: nothing prior, expected id 0
    p1 = await relay_ops.begin_turn(claude, "t1")
    assert p1.expected_last_turn_id == 0
    assert p1.prior_events == []

    # 3. claude submits -> baton to codex, real write
    r1 = await relay_ops.submit_turn(claude, p1.turn_token, "Claude: use an LRU.",
                                     next_baton="codex")
    assert r1.created is True
    assert r1.baton == "codex"

    # 4. replay the SAME token -> idempotent: not created, same turn id, still one turn
    r1b = await relay_ops.submit_turn(claude, p1.turn_token, "Claude: use an LRU.",
                                      next_baton="codex")
    assert r1b.created is False
    assert r1b.turn_id == r1.turn_id

    # 5. codex begins (sees claude's turn) + submits -> baton back to claude
    p2 = await relay_ops.begin_turn(codex, "t1")
    assert p2.expected_last_turn_id == 1
    assert [e.author for e in p2.prior_events] == ["claude"]
    r2 = await relay_ops.submit_turn(codex, p2.turn_token, "Codex: add a TTL.",
                                     next_baton="claude")
    assert r2.created is True

    # 6. events show exactly two alternating authors
    evs = await relay_ops.events(claude, "t1", 0)
    assert [e.author for e in evs] == ["claude", "codex"]

    # 7a. wrong-baton begin is rejected (baton is claude's now; codex tries)
    with pytest.raises(ValueError, match="not_your_turn"):
        await relay_ops.begin_turn(codex, "t1")

    # 7b. a typo'd next_baton is rejected locally, before any write
    p3 = await relay_ops.begin_turn(claude, "t1")
    with pytest.raises(ValueError, match="unknown_next_baton"):
        await relay_ops.submit_turn(claude, p3.turn_token, "x", next_baton="ghost")
    # the typo wrote nothing: still two turns on the thread
    assert (await relay_ops.status(claude, "t1")).last_turn_id == 2


async def test_halt_then_resume_cycle_through_the_router(agents) -> None:
    claude, codex = agents
    await relay_ops.start(claude, "Design the cache", first_agent="claude", thread_id="t2")
    p1 = await relay_ops.begin_turn(claude, "t2")

    # claude halts for a human (atomic): thread leaves 'active', baton stays claude
    halt = await relay_ops.halt_turn(claude, p1.turn_token, "I need a decision",
                                     status="needs_human", question="SQLite or Postgres?")
    st = await relay_ops.status(claude, "t2")
    assert st.status == "needs_human" and st.baton == "claude"
    assert st.last_turn_id == halt.turn_id
    # while halted, the wake predicate (status=='active') is false -> no driver would fire

    # operator (codex as human proxy) answers and reactivates, handing the baton to claude
    resumed = await codex.resume_turn("t2", "Use SQLite.", "claude", "resume-1",
                                      halt.turn_id, halt.turn_id)
    st2 = await relay_ops.status(claude, "t2")
    assert st2.status == "active" and st2.status_reason is None
    assert st2.baton == "claude" and st2.last_turn_id == resumed["id"]

    # the thread is live again: claude can take its turn, and sees both halt + answer
    p2 = await relay_ops.begin_turn(claude, "t2")
    assert [e.author for e in p2.prior_events] == ["claude", "codex"]

    # resume is idempotent and refuses to re-fire on an already-active thread
    again = await codex.resume_turn("t2", "Use SQLite.", "claude", "resume-1",
                                    halt.turn_id, halt.turn_id)
    assert again["id"] == resumed["id"]
