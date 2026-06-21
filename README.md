# Agent Relay Plugin

This repository is becoming the plugin-centered home for the Agent Relay experience:
turn-based collaboration between Claude Code and Codex on a shared local thread.
The collaboration is coordinated by a local single-writer router that enforces baton
ownership, leases, idempotent turn submission, and optional wake support.

Current status: the working implementation still lives in the sibling `Agent-Slack`
repository. This repo is being shaped into the cleaner standalone home for the
plugin layer, packaging, and documentation.

## What This Repository Will Be

This repo is intended to own the plugin-facing experience:

- plugin packaging and installation docs for Claude and Codex
- the MCP server surface for relay operations
- agent-facing collaboration skills and workflows
- setup guidance for running the plugin against a local router
- lightweight contributor context explaining how the plugin fits into the wider system

Long-term, this repo is not intended to be:

- the sole home of the router database or backend runtime
- the full wake-driver and VS Code extension monorepo
- a generic multi-agent orchestration platform beyond the relay use case

## How Collaboration Works

1. One agent starts a relay thread for a task.
2. The current baton-holder claims the turn and receives an opaque turn token.
3. That agent submits one idempotent turn and hands the baton to the peer.
4. The peer is nudged by a human or an optional wake watcher.
5. The loop continues until the thread reaches `done`, `blocked`, or `needs_human`.

The important guarantees are:

- one local router is the single writer and source of truth
- only one agent holds the active baton at a time
- turn ownership is protected by leases
- retries are safe through idempotent submission
- halts and resumes happen atomically so the thread state stays coherent

## Documented MCP Surface

The plugin-facing MCP surface is centered on these relay tools:

| Tool | Purpose |
|---|---|
| `relay_start` | Open a collaboration thread and assign the first baton. |
| `relay_begin_turn` | Verify the baton, acquire the lease, and return the turn token plus prior events. |
| `relay_submit_turn` | Record one turn and hand the baton to the peer. |
| `relay_halt_turn` | Record a turn and atomically pause the thread for `needs_human` or `blocked`. |
| `relay_status` | Read the routing state for a thread. |
| `relay_events` | Read the event history for a thread. |

These six tools reflect the current implementation surface, including
`relay_halt_turn`.

## Architecture In Context

The plugin depends on a few companion runtime pieces:

- a local FastAPI + SQLite router that arbitrates baton, lease, idempotency, and thread state
- an optional per-agent wake driver that watches router events and nudges the next agent
- an optional VS Code notification extension for human visibility

For now, those runtime pieces live in the sibling `Agent-Slack` repository.
This repo is intended to become the plugin-centered home and primary entrypoint for
the collaboration layer that sits on top of them.

## Current Status

Today this repo is still a scaffold and documentation-first workspace.

- the sibling `Agent-Slack` repo contains the working implementation
- this README describes the intended extracted plugin product and its boundaries
- setup and smoke-test instructions still come from the sibling repo until extraction is complete

That distinction is intentional: this README should help readers understand where the
plugin is headed without implying that the runtime already lives here.

## Near-Term Repository Shape

As the extraction continues, this repo is expected to grow into a focused plugin home
with:

- plugin server code
- agent skills and plugin manifests
- plugin-specific tests
- standalone install and usage docs
- examples and smoke-test guidance

## Getting Started Today

If you want to run the system now, use the sibling `Agent-Slack` repository.
That repo currently holds the working router, the relay plugin implementation, the
wake-driver support, and the runtime documentation.

Until the extraction is complete:

- use `Agent-Slack` for setup and smoke-test instructions
- use its plugin and runtime docs as the operational source of truth
- expect this README to become the primary plugin entrypoint once the code is moved here
