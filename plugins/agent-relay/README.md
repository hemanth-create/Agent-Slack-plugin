# Agent-Relay plugin

Lets **Claude Code** and **Codex** collaborate by taking alternating turns on a shared
thread, arbitrated by the local single-writer relay router. The plugin is a thin **stdio
MCP server** (`server/`) that wraps the already-shipped router HTTP routes — no router or
DB changes. The router stays the sole authority for baton, lease, CAS, and idempotency.

## The five tools

| Tool | Purpose |
|---|---|
| `relay_start(task, first_agent)` | Create a collaboration thread; baton goes to `first_agent`. |
| `relay_begin_turn(thread_id)` | Claim your turn: verify baton → lease → re-verify baton (TOCTOU) → read thread. Returns an opaque `turn_token`. |
| `relay_submit_turn(turn_token, body, next_baton)` | Record your turn (one idempotent write) and hand the baton to `next_baton`. Halts go in the body text. |
| `relay_status(thread_id)` | Read routing state: status, baton, last turn id. |
| `relay_events(thread_id, since)` | List the thread's turns. |

Two skills drive the loop: **collaborate** (start + first turn) and **continue** (take one
turn when the baton is yours).

## Design guarantees

- **One idempotent write per turn.** A `turn_token` pins the lease id, the expected last
  turn id, and a single idempotency key, so a retried submit replays safely (no double
  post, no spurious 409). All halts (`needs_human`/`done`) are in-body text — there is no
  status call in v1 (a status call would break that idempotency and has no honest reason
  value in the schema).
- **No stranded threads.** `next_baton` is validated locally against the allowed agents
  before any write (a typo would otherwise strand the thread — the router has no re-baton
  route). A double-read baton guard around lease acquire closes the TOCTOU window.
- **Assisted wake.** An MCP server is a callee; it cannot wake a dormant peer. After you
  submit, a human (or a per-agent WS watcher on the router's `/ws`) nudges the other agent.

## Config (host env)

`RELAY_API_KEY` (this agent's bearer token — never committed) is read from the host
environment. `RELAY_AGENT_ID`, `RELAY_ALLOWED_AGENTS`, `RELAY_BASE_URL`, and
`RELAY_LEASE_TTL_SECONDS` come from the MCP config (`.mcp.json` for Claude,
`codex-config-snippet.toml` for Codex). The server **fails fast** if `RELAY_API_KEY` is missing.

See [docs/run-relay-plugin.md](../../docs/run-relay-plugin.md) for the install + smoke runbook.
