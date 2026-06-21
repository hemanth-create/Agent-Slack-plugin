# Agent-Slack

[![CI](https://github.com/hemanth-create/Agent-Slack-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/hemanth-create/Agent-Slack-plugin/actions/workflows/ci.yml)
[![docs](https://github.com/hemanth-create/Agent-Slack-plugin/actions/workflows/docs-checks.yml/badge.svg)](https://github.com/hemanth-create/Agent-Slack-plugin/actions/workflows/docs-checks.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**A local, single-writer relay that lets two AI coding agents (Claude Code + Codex) collaborate by taking turns on one shared thread — no cloud service, no shared-file race.**

Think of it as a shared notebook with a single talking stick: only the agent holding the baton may write, then it hands the baton to the other. A small local router is the referee — it is the *only* writer, so two agents editing at once can never corrupt the conversation.

---

## What it is

Agent-Slack is a FastAPI + SQLite **router** that arbitrates a turn-based conversation between AI agents:

- **`data/router.db` (SQLite) is the sole source of truth.** Agents never write files directly; they submit structured turns over HTTP. `thread.md` / `state.json` are *generated projections*, never read for routing.
- Every turn is accepted inside **one `BEGIN IMMEDIATE` transaction** that checks, in fixed order: auth → idempotency → status → baton → compose-lease → optimistic concurrency → append → baton hand-off. This makes concurrent writers safe and turns idempotent.
- Agents reach the router through a tiny **MCP plugin** (`relay_*` tools), so Claude Code and Codex can drive it natively.
- An optional **wake-driver** subscribes to the router's WebSocket and spawns one headless agent turn each time the baton lands on it — turning the manual relay into a hands-free loop.

## Architecture

| Component | What it is |
|-----------|------------|
| [`router/`](router/) | The FastAPI single-writer backend. Owns `data/router.db`, the accept transaction, leases, idempotency, projections, and the HTTP/WebSocket API. The authority. |
| [`plugins/agent-relay/`](plugins/agent-relay/) | The MCP plugin agents install — a thin stdio server exposing `relay_start`, `relay_begin_turn`, `relay_submit_turn`, `relay_halt_turn`, `relay_status`, `relay_events`. |
| [`wake_driver/`](wake_driver/) | The hands-free runtime. One process per agent; watches `/ws` and spawns a single headless turn per wake. |
| [`extension/`](extension/) | A VS Code extension (TypeScript) that connects to the router over WebSocket and notifies you when it's your agent's turn. |
| [`experimental/orchestrator/`](experimental/orchestrator/) | An earlier orchestration prototype, **superseded by `wake_driver/`** and kept for reference only — not part of the supported runtime. |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces connect, and [`AGENTS.md`](AGENTS.md) for the locked v0 architecture invariants.

## Quick start

> **Run from a local, non-synced folder.** SQLite with WAL is unreliable on OneDrive/Dropbox/iCloud paths, and the router will refuse to start there by design.

**1. Install** (Python 3.12+):

```bash
python -m venv venv
# Windows: venv\Scripts\activate   •   macOS/Linux: source venv/bin/activate
pip install -e ".[dev]"     # or: pip install -r requirements.txt
```

**2. Initialize the database and local auth tokens:**

```bash
python -m scripts.init_db
python -m scripts.init_auth      # writes bearer tokens to data/secrets.json (gitignored)
```

**3. Run the router:**

```bash
python -m uvicorn router.api.app:app --host 127.0.0.1 --port 8000
# health check:  GET http://127.0.0.1:8000/health
```

**4. Connect the agents.** Install the relay MCP plugin in each agent so they get the `relay_*` tools — see [`plugins/agent-relay/README.md`](plugins/agent-relay/README.md) and [`docs/run-relay-plugin.md`](docs/run-relay-plugin.md). Then either drive turns manually or start the hands-free wake-driver (one process per agent):

```bash
# copy .env.example -> .env (or bank machine paths in data/local_config.json), then:
WAKE_AGENT_ID=claude WAKE_THREAD_ID=demo python -m wake_driver.run
WAKE_AGENT_ID=codex  WAKE_THREAD_ID=demo python -m wake_driver.run
```

A full HTTP walkthrough (create thread, acquire lease, submit a turn, inspect projections) and the VS Code wake smoke are in [`docs/run-local.md`](docs/run-local.md).

## Security model

- **Local-only.** The router binds to loopback; there is no cloud broker. All state lives in `data/` on your machine.
- **Bearer auth on every request** (HTTP and WebSocket). The acting agent is derived from its token, never self-asserted; WebSocket `Origin` is validated.
- **Secrets never ship.** `data/` (tokens, DB, `local_config.json`) is gitignored; committed config files use placeholders only. See [`SECURITY.md`](SECURITY.md) to report a vulnerability.
- **Agents stay sandboxed.** When run headless, only the `relay_*` tools are trusted — arbitrary shell stays under the agent's own sandbox policy.

## Project layout

```
router/                 FastAPI single-writer backend (api/ config/ db/ projections/)
plugins/agent-relay/    MCP plugin: relay_* tools + collaborate/continue skills
wake_driver/            hands-free per-agent turn spawner
extension/              VS Code extension (TypeScript)
scripts/                init_db, init_auth, probes, smoke tests
tests/                  pytest suite (the supported, default-collected suite)
docs/                   architecture, run guides, design history
experimental/           archived, unsupported prototypes
```

## Development

```bash
ruff check .            # lint (config in pyproject.toml)
pytest                  # run the supported suite
```

> On a synced (OneDrive/Dropbox) checkout, point pytest at a non-synced temp dir so the
> router's sync-root guard doesn't trip: `pytest --basetemp="$TMPDIR/agent-slack"`.

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). Coding standards live in [`AGENTS.md`](AGENTS.md).

## License

[MIT](LICENSE) © 2026 hemanth-create
