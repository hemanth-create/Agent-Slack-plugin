# Running the Agent-Relay plugin (install + smoke)

Two real agent sessions — Claude Code and Codex — take alternating turns on a shared relay
thread. The plugin is a stdio MCP server (`plugins/agent-relay/server/`) that wraps the running
router; the router is the sole authority and the plugin adds no DB state.

Throughout, **`<REPO>`** is your local checkout (a local, **non-synced** folder) and **`<PYTHON>`**
is an interpreter that has `mcp` installed (e.g. your activated venv's `python`).

## 0. Prerequisites

- **Router running** from `<REPO>` (a non-synced folder — a SQLite DB on OneDrive/Dropbox is a
  corruption hazard, and the router refuses to start there):
  ```
  python -m uvicorn router.api.app:app --host 127.0.0.1 --port 8000
  ```
  Confirm: `GET http://127.0.0.1:8000/health` → `{"status":"ok",...}`.
- **`mcp` installed** in that interpreter: `<PYTHON> -c "from mcp.server.fastmcp import FastMCP"`.
- **Both bearer tokens** in `data/secrets.json` (`{"agents":{"claude":"...","codex":"..."}}`).
  Never commit these.

## 1. (Recommended) Automated stdio-MCP smoke

Before wiring real agents, prove the packaged server talks to the router as two agents:

```
<PYTHON> -m scripts.smoke_relay_mcp
```

Expect `PASS: two agents alternated over real stdio MCP`. This launches the server exactly as
the MCP configs below do, so a green run means the configs are sound.

## 2. Install in Claude Code

`RELAY_API_KEY` is read from the host env (not the committed `.mcp.json`). The plugin's
`.mcp.json` points `command` at your interpreter and `cwd` at `${CLAUDE_PLUGIN_ROOT}`.

```powershell
# Windows PowerShell
$env:RELAY_API_KEY = "<claude token from data/secrets.json>"
$env:MCP_TIMEOUT   = "120000"   # generous stdio startup window
claude --plugin-dir "<REPO>/plugins/agent-relay"
```

In session, `/mcp` should list the `relay` server with the `relay_*` tools; `/reload-plugins`
re-reads the plugin after edits.

## 3. Install in Codex

Codex reads MCP servers from `~/.codex/config.toml` (not `.mcp.json`) and does **not** interpolate
`${CLAUDE_PLUGIN_ROOT}`. Append the block from `plugins/agent-relay/codex-config-snippet.toml`,
filling in `<PYTHON>`, `<PLUGIN_ROOT>`, and `<CODEX_TOKEN>`, then launch Codex with **its** token:

```powershell
$env:RELAY_API_KEY = "<codex token from data/secrets.json>"
codex
```

> Verified with codex-cli 0.141.0. If the `[mcp_servers]` schema has drifted in your build, that
> surfaces at launch — note the exact error and adjust the snippet.

## 4. Run the collaboration

1. In **Claude**: invoke the `collaborate` skill — "collaborate with Codex on \<task>, I go first."
   Claude calls `relay_start(task, first_agent="claude")`, reports the `thread_id`, then
   `relay_begin_turn` → works → `relay_submit_turn(next_baton="codex")`.
2. Get the baton to **Codex** (see §5) with the `thread_id`. Invoke the `continue` skill — Codex
   confirms the baton via `relay_status`, takes its turn, hands back.
3. Repeat. Watch the thread via `relay_events(thread_id)` from either side.

## 5. Getting the baton to the other agent

A bare MCP server is a callee — it cannot wake a dormant peer. Two options:

- **Human in the loop (simplest):** tell the other agent "your turn on \<thread_id>."
- **Wake-driver (hands-free):** run `wake_driver` — one process per agent. Each subscribes to the
  router `/ws` and spawns that agent's turn when `status==active ∧ baton==thatAgent ∧ head advanced`.
  See the [README](../README.md) and [ARCHITECTURE](ARCHITECTURE.md).

## 6. Halts (pause for a human)

An agent can pause the thread with **`relay_halt_turn`** (`status="needs_human"` or `"blocked"`
plus a `question`); the router flips the thread to a recovery state, the human answers, and the
thread resumes. (Submitting a turn with `status="needs_human"` also works.)

## Troubleshooting

- **`RELAY_API_KEY is required`** on startup → you didn't export the token in the launching shell;
  it is deliberately not in any committed file.
- **Tools missing in `/mcp`** → check `MCP_TIMEOUT`, then run the §1 smoke; a failure there isolates
  the problem to the server/router rather than the agent host.
- **`not_your_turn` / `baton_changed`** → it's the peer's move, or the baton shifted under you.
  Re-check `relay_status` instead of forcing a write.
