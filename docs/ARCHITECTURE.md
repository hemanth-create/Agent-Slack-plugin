# Architecture

Agent-Slack arbitrates a turn-based conversation between AI agents through a single local
writer. This document explains how the pieces fit; the locked, language-agnostic invariants
live in [`../AGENTS.md`](../AGENTS.md).

## The one rule: a single writer owns the truth

`data/router.db` (SQLite) is the **sole source of truth**. Agents never edit shared files;
they submit structured turns over HTTP and the router is the only process that writes. This
is what makes concurrent agents safe — there is no shared-Markdown race to lose.

`thread.md` and `state.json` under `data/projections/<thread>/` are **generated projections**:
regenerable, never read for routing decisions, never written by agents. If they are deleted,
the next turn (or a projection drain) recreates them from `router.db`.

## Components

```
        ┌─────────────┐   relay_* MCP tools    ┌──────────────────────┐
Claude ─┤ agent-relay ├───────HTTP/WS─────────►│                      │
        └─────────────┘                        │   router/ (FastAPI)  │
        ┌─────────────┐                        │   single writer      │──► data/router.db
Codex ──┤ agent-relay ├───────HTTP/WS─────────►│   accept transaction │     (authority)
        └─────────────┘                        │   leases · baton     │
              ▲                                 └──────────┬───────────┘
              │ spawns one headless turn per wake          │ WS: "your turn"
        ┌─────┴───────┐                                    ▼
        │ wake_driver │◄──────────── /ws baton frames ──── extension/ (VS Code notify)
        └─────────────┘
```

- **`router/`** — FastAPI app (`router.api.app:app`). Subpackages: `api/` (HTTP + WS routes),
  `config/` (startup checks, credentials), `db/` (all SQL — schema, the accept transaction,
  leases, projections), `projections/` (Markdown/JSON renderers). Opens exactly one writer
  connection at startup and serializes turn acceptance behind a writer lock.
- **`plugins/agent-relay/`** — the MCP server agents load. Its `relay_*` tools are thin wrappers
  over the router's HTTP routes, so Claude Code and Codex can drive the relay natively. Ships
  with `collaborate` / `continue` skills.
- **`wake_driver/`** — one process per agent. It subscribes to the router's WebSocket and, when
  a frame shows `status=active ∧ baton=me`, spawns a single headless agent turn (the relay thread
  *is* that turn's memory), then idles until the next wake. Machine-specific values resolve via
  `local_config.py` (env → gitignored `data/local_config.json` → default).
- **`extension/`** — a VS Code extension that holds the token in SecretStorage and notifies you
  in-editor when a watched thread's baton reaches your agent.

## The accept transaction

Every turn is accepted inside **one `BEGIN IMMEDIATE`** with a fixed gate order; any failed gate
rolls the whole thing back:

1. **Authenticate** — the acting agent is derived from its bearer token, never self-asserted.
2. **Idempotency** — `(thread_id, agent, idempotency_key)` hit returns the stored result and exits;
   a same-key/different-payload collision is a `409 idempotency_conflict`.
3. **Status** — the thread must be `active`.
4. **Baton** — the caller must currently hold the baton.
5. **Lease** — the caller must hold a live compose lease.
6. **Optimistic concurrency** — `expected_last_turn_id` must match the current head (CAS).
7. **Append + hand off** — write the turn (server-assigned id), advance the cursor, flip the baton,
   enqueue the outbox, mark projections dirty.
8. **Commit**, then regenerate projections post-commit (a projection failure never rolls back the turn).

**Leases** are acquired before composing and renewed by heartbeat; on expiry the thread flips to
`needs_human` (no silent auto-reroute in v0). **Halt/resume** is a single atomic transition so a
thread is never left in an `active ∧ baton=self` window.

## Hands-free loop

The manual relay (a human passing the baton) and the automated loop share the same router and
gates. In the automated loop, each agent's `wake_driver` reacts to a `/ws` wake by spawning one
headless turn that calls `relay_begin_turn` → `relay_submit_turn` and hands the baton back. Turn
completion is judged from **router state** (`relay_status`), not the spawned CLI's stdout.

## Security model

Loopback-only binding; bearer auth on every HTTP and WebSocket request with `Origin` validation;
`data/` (tokens, DB, `local_config.json`) is gitignored and never committed; committed config files
carry placeholders only. Headless agents trust only the `relay_*` tools — arbitrary shell stays
under the agent's own sandbox policy. See [`../SECURITY.md`](../SECURITY.md).

## Status

`router/`, `plugins/agent-relay/`, and `wake_driver/` are the supported runtime.
[`../experimental/orchestrator/`](../experimental/orchestrator/) is an earlier prototype, superseded
by `wake_driver/` and excluded from the default test run — kept for design reference only.
