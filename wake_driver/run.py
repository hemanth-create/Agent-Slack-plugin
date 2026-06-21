"""Live wake-driver entrypoint: subscribe to /ws and drive one real turn per wake.

One process per agent. Set WAKE_AGENT_ID + WAKE_THREAD_ID, then:
    python -m wake_driver.run
The router must be running and data/secrets.json must hold this agent's token.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugins" / "agent-relay"))

import httpx  # noqa: E402

from server import relay_ops  # noqa: E402
from server.router_api import RouterApi  # noqa: E402

from wake_driver.codex_home import write_codex_home  # noqa: E402
from wake_driver.config import Config, load_config  # noqa: E402
from wake_driver.local_config import secrets_path  # noqa: E402
from wake_driver.driver import decide_next, drive_once, halt_thread  # noqa: E402
from wake_driver.guard import should_act  # noqa: E402
from wake_driver.lock import acquire_singleflight, release_singleflight  # noqa: E402
from wake_driver.relay_config import write_relay_mcp_config  # noqa: E402
from wake_driver.spawn import (  # noqa: E402
    _resolve_bin, claude_argv, codex_argv, prompt_for, run_turn,
)
from wake_driver.state import StateStore  # noqa: E402
from wake_driver.ws_listen import wake_stream  # noqa: E402

_OTHER = {"claude": "codex", "codex": "claude"}


def _log(msg: str) -> None:
    print(f"[wake-driver] {msg}", file=sys.stderr, flush=True)


def _api(cfg: Config) -> RouterApi:
    client = httpx.AsyncClient(
        base_url=cfg.base_url, headers={"Authorization": f"Bearer {cfg.token}"}
    )
    return RouterApi(client, cfg.agent_id, frozenset({"claude", "codex"}), cfg.lease_ttl)


def _spawn(cfg: Config, workdir: Path):
    """Return an async no-arg callable that runs exactly one headless turn for this agent."""
    prompt = prompt_for(cfg.thread_id, _OTHER[cfg.agent_id])
    if cfg.agent_id == "claude":
        mcp = write_relay_mcp_config(workdir / "relay.json", "claude", cfg.base_url)
        claude_bin = _resolve_bin(os.environ.get("WAKE_CLAUDE_BIN", "claude"))
        argv = claude_argv(claude_bin, str(mcp))
        env = {**os.environ, "RELAY_API_KEY": cfg.token, "MCP_TIMEOUT": "120000"}
    else:
        codex_bin = _resolve_bin(os.environ.get("WAKE_CODEX_BIN", "codex"))
        argv = codex_argv(codex_bin, str(workdir), str(workdir / "last.txt"))
        home = write_codex_home(REPO / "data" / "wake_driver" / "codex_home",
                                cfg.base_url, cfg.token, Path.home() / ".codex")
        env = {**os.environ, "CODEX_HOME": home}

    async def spawn() -> None:
        await asyncio.to_thread(run_turn, argv, prompt, env, str(workdir), cfg.spawn_timeout)

    return spawn


async def _status_dict(api: RouterApi, thread_id: str) -> dict:
    state = await relay_ops.status(api, thread_id)
    return {"status": state.status, "baton": state.baton, "last_turn_id": state.last_turn_id}


async def _drive(cfg: Config, api: RouterApi, before_head: int, store: StateStore, last: int) -> int:
    workdir = Path(tempfile.mkdtemp(prefix=f"wake-{cfg.agent_id}-"))
    try:
        cls = await drive_once(cfg.agent_id, before_head, _spawn(cfg, workdir),
                               lambda: _status_dict(api, cfg.thread_id))
        nxt = decide_next(cls)
        _log(f"turn classified '{cls}' -> {nxt}")
        if nxt == "advance":
            new = (await relay_ops.status(api, cfg.thread_id)).last_turn_id
            store.advance(new)
            return new
        if nxt == "escalate":
            await halt_thread(api, cfg.thread_id, f"escalate: {cls}")
        return last
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def run(cfg: Config) -> None:
    """Subscribe to /ws and drive one turn per wake until interrupted."""
    api = _api(cfg)
    seed = await relay_ops.status(api, cfg.thread_id)
    base = REPO / "data" / "wake_driver"
    store = StateStore(base / f"{cfg.agent_id}-{cfg.thread_id}.json")
    st = store.seed(seed.last_turn_id)
    start_id, last = st["start_id"], st["last_processed"]
    lock_path = str(base / f"{cfg.agent_id}-{cfg.thread_id}.lock")
    base.mkdir(parents=True, exist_ok=True)
    _log(f"watching {cfg.thread_id} as {cfg.agent_id} (start_id={start_id})")
    while True:
        try:
            async for _frame in wake_stream(cfg.ws_url, cfg.thread_id, cfg.token):
                sd = await _status_dict(api, cfg.thread_id)
                decision = should_act(sd, cfg.agent_id, last, start_id, cfg.max_turn_cap)
                if decision == "halt_cap":
                    await halt_thread(api, cfg.thread_id, "max-turn cap reached")
                elif decision == "act":
                    lock = acquire_singleflight(lock_path)
                    if lock is None:
                        continue
                    try:
                        last = await _drive(cfg, api, sd["last_turn_id"], store, last)
                    finally:
                        release_singleflight(lock)
        except Exception as exc:  # noqa: BLE001 - reconnect on any stream error
            _log(f"stream error: {exc!r}; reconnecting in 2s")
            await asyncio.sleep(2)


def main() -> None:
    cfg = load_config(dict(os.environ), secrets_path())
    asyncio.run(run(cfg))


if __name__ == "__main__":
    main()
