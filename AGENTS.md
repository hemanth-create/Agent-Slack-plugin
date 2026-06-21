# AGENTS.md — Local Multi-Agent Relay Router

Read this before writing any code in this repo. It is the source of truth for stack, architecture, coding standards, and agent roles.

> **New here?** Start with [`README.md`](README.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). This file is the contributor/agent guide for working *in* the repo.

## What this project is
A **local, single-writer backend** that lets multiple AI coding agents (currently Claude + Codex) collaborate on one thread without a shared cloud service. Agents submit structured turns; the backend is the only writer; `thread.md` / `state.json` are generated **projections**, never the source of truth. Architecture overview: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repo path
Clone or copy this repo to any local, **non-synced** folder. Do **not** run it from a OneDrive/Dropbox/iCloud-synced path (see the sync-folder hazard below) — SQLite WAL+FULL is unreliable there.

## Stack — Python + FastAPI
- Backend runtime: **Python 3.11+** with **FastAPI** + **uvicorn**.
- Storage: **SQLite** via stdlib `sqlite3` (or `aiosqlite` for async); authority = `data/router.db`.
- Models/validation: **Pydantic** (alias-based snake_case ↔ camelCase).
- WebSocket: FastAPI's native WebSocket support.
- Notifications: a local desktop notifier (e.g. `plyer`/`win10toast`); no Slack unless explicitly opted in.

> **One component cannot be Python:** the VS Code router extension runs in VS Code's Node-based extension host, so it **must be TypeScript/JavaScript**. Backend, hook script, and tooling are Python; the extension is TS. Hard platform constraint, not a choice.

## Data location — inside the repo
- DB and secrets live under **`<repo>/data/`** (`data/router.db`, `data/secrets.json`).
- **`data/` is `.gitignore`d** — the auth token and DB are never committed.
- **Sync-folder hazard:** SQLite on a OneDrive/Dropbox-synced folder risks corruption and lock contention. The P0 probe must confirm this repo path is **not** on a sync root before any DB is created. If it is synced, stop and decide (move the repo, or accept the risk).

## Locked v0 architecture invariants (language-agnostic — do not violate)
- `data/router.db` is the **sole authority**. `thread.md` + `state.json` are regenerable projections — never read for routing truth, never written by agents.
- PRAGMAs re-applied on **every connection open** (connection-scoped): `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`, `busy_timeout`. **Startup-only DB gates** (read once at init, not per-open): `user_version` (migrate-or-refuse) and `quick_check` (full-DB integrity scan — too costly to run on every open).
- **Auth:** bearer token on every HTTP + WS request via a `verify_api_key`-style dependency; `auth_agent` derived from the token, never self-asserted; validate WS `Origin`.
- **Accept transaction — one `BEGIN IMMEDIATE`, fixed order:** authenticate → idempotency lookup `(thread_id, auth_agent, key)` (hit ⇒ return stored, exit) → status==active → baton → lease → CAS `last_turn_id` → reply_to/read-coverage → append (server id) → advance cursor + flip baton + outbox + mark projections dirty → store idempotency → commit → post-commit projection regen (never rolls back).
- **Idempotency:** UNIQUE `(thread_id, auth_agent, idempotency_key)` + payload hash; same key, different hash → `409 idempotency_conflict`.
- **Leases:** acquire before composing; renew via heartbeat; expiry → `needs_human` + `status_reason=disconnected`; no auto-reroute in v0.
- **Status:** `active | needs_human | blocked | done | cancelled` + a `status_reason` discriminator; transitions keyed on `(status, status_reason)`.
- **Path/scope checks:** canonicalize (resolve `..`, normalize Windows case, reject symlink escapes and rename-headers outside scope) before any `allowed_paths` membership test.

## Coding standards (enforced from the first commit)
- **Production-grade only** — no "clean it up later", no hand-wavy TODO implementations.
- **Files ≤ 150 LOC** (hard limit 200). **Functions ≤ 15–20 LOC** (hard limit 20).
- **Names say exactly what they do** — `accept_turn.py` not `turns.py`, `validate_baton.py` not `utils.py`. One responsibility per file.
- **Type hints everywhere**; lint/format with `ruff`.
- **Pydantic** models for every request/response; alias-based snake↔camel; don't hand-map fields.
- Shared DB access via a dependency (e.g. `dependencies.get_db`); routes never open their own connections.
- Wrap synchronous `sqlite3` calls in **`asyncio.to_thread(...)`** inside async routes.
- All SQL lives in a `db/` layer; **no raw SQL in routes**.
- Route handlers ≤ 20 lines — logic lives in service functions. The accept transaction lives entirely in one module.
- A `pytest` test accompanies each behavioral change.

> This router has no tenants, analytics, or dashboards — only the general Python/FastAPI conventions in this document apply.

## Roles
> Team as of 2026-06-19: **Claude + Codex only** (Kiro removed from the loop). Re-add Kiro only if the human brings it back.
- **Claude (Opus 4.8) — Architect / Lead + author:** canonical plan, architecture decisions, security/transition review, merge gate. Authors task slices directly into the repo (bootstrap mechanism B).
- **Codex (GPT-5) — Implementer + co-architect + reviewer/verifier:** backend / schema / API / projection / tests from Claude's approved slices (small diffs); reviews Claude's diffs against the invariants and runs `pytest` in its venv as the second check.
- **QA / integration:** no dedicated agent — verification is the human running the commands + Codex's venv run + Claude's review. The real integrator is the backend itself (single-writer router), not an agent seat.

## Process (until the single-writer backend exists)
- Real concurrent-write race on shared Markdown → **invoke agents one at a time, serially.** The backend's single-writer model removes this permanently.
- Order per change: Lead authors a slice → Codex reviews + verifies in its venv → the human runs the commands → repeat. (Phase 0 probes are complete.)
- **Phase 0 probes gate all app code** — no Phase 1 until `docs/probe-results.md` exists.

## Build phases (canonical)
- **P0 — Probes (blocking):** Python `sqlite3` PRAGMA compliance on Windows; **repo-path sync-root check**; `os.replace` atomic-over-open-file; Kiro hook cwd/exit/double-fire; extension manifests; Python/venv availability → `docs/probe-results.md`.
- **P1 — Backend foundation:** repo layout, `data/router.db` schema, PRAGMA init, startup checks (sync-root refusal, port conflict, `quick_check`), config + gitignored secrets.
- **P2 — Auth + accept transaction + API:** bearer auth, the 13-step transaction, idempotency, leases, projections, inbox drainer, FastAPI HTTP/WS endpoints.
- **P3 — Agent connector (was Kiro hook):** generic submit path (`inbox/<agent>-draft.md` + `submission_id` → Python submit script). Deferred now that Kiro is out; revisit when a connector is needed.
- **P4 — Router VS Code extension (TypeScript):** WS client, identity register, notifications, prompt preload.
- **P5 — E2E smoke test.**
- **P6 — Plan/task layer:** plan/task tables, canonicalized scope check, the verification gate.
