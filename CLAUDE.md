# CLAUDE.md

This repo follows **[AGENTS.md](./AGENTS.md)** — read it first. It defines the stack (**Python + FastAPI + SQLite**), the locked v0 architecture invariants, the coding standards, and the agent roles.

## Role
Claude is **Architect / Lead**: owns the canonical plan, architecture and security review, and the merge gate. Claude authors task slices; Codex implements them; Kiro runs probes/QA.

## Claude-Code-specific notes
- Cross-agent collaboration uses the `/agent-relay` skill (shared-Markdown relay). Architecture overview: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- **Concurrency:** until the single-writer backend is built, never edit shared Markdown concurrently with other agents. Invoke serially; append turns at the file bottom; re-read the tail before writing.
- **Stack:** backend is **Python + FastAPI + sqlite3** (Pydantic, `verify_api_key` auth dependency, `asyncio.to_thread` around sync DB calls). The **VS Code router extension is unavoidably TypeScript** (VS Code's extension host is Node).
- **Data lives in `<repo>/data/`** (gitignored) — but a SQLite DB on a synced (OneDrive) folder is a corruption hazard; the P0 probe must confirm the repo isn't synced before any DB is created.
- **Hard coding limits:** files ≤150 LOC (max 200), functions ≤15–20 LOC (max 20), type hints, `ruff`, Pydantic models, no raw SQL outside `db/`, explicit names.
