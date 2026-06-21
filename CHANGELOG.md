# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-06-20

Initial public release.

### Added
- **Single-writer router** (`router/`): FastAPI + SQLite backend where `data/router.db` is the sole
  source of truth. Turn acceptance runs in one `BEGIN IMMEDIATE` transaction with auth, idempotency,
  status, baton, lease, and optimistic-concurrency gates; `thread.md` / `state.json` are generated
  projections.
- **Compose leases, baton hand-off, and atomic halt/resume** with `needs_human` recovery.
- **HTTP + WebSocket API** with bearer auth and `Origin` validation.
- **Agent-Relay MCP plugin** (`plugins/agent-relay/`): `relay_start`, `relay_begin_turn`,
  `relay_submit_turn`, `relay_halt_turn`, `relay_status`, `relay_events`, plus collaborate/continue
  skills, for Claude Code and Codex.
- **Wake-driver** (`wake_driver/`): one process per agent that watches `/ws` and spawns a single
  headless turn per wake, for hands-free alternating collaboration. Machine-specific values resolve
  via `local_config.py` (env → gitignored `data/local_config.json` → default).
- **VS Code extension** (`extension/`): WebSocket client that notifies you when it's your turn.
- Packaging (`pyproject.toml`), CI (ruff + pytest on Windows/3.12), and project docs.

[Unreleased]: https://github.com/hemanth-create/Agent-Slack-plugin/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hemanth-create/Agent-Slack-plugin/releases/tag/v0.1.0
