---
name: collaborate
description: Use when the user wants to start a collaboration with the other AI agent (Claude <-> Codex) on a task. Opens a shared relay thread and takes the first turn.
---

# Start a relay collaboration

You and the other agent (Claude or Codex) take alternating turns on a shared thread,
arbitrated by the local relay router. One agent holds the **baton** at a time; only the
baton-holder may write. You reach the thread through the `relay_*` MCP tools.

## Protocol (one turn at a time)

1. **Start** — call `relay_start(task, first_agent)`. `first_agent` should be **you**
   (the agent the user asked to begin). It returns `{thread_id, baton, last_turn_id}`.
   Tell the user the `thread_id` and ask them to point the other agent at it.

2. **Take your turn** — call `relay_begin_turn(thread_id)`. This verifies the baton is
   yours, leases the thread, and returns `prior_events` plus an opaque `turn_token`.
   - If it raises `not_your_turn`, it is the peer's move — stop and wait.

3. **Think, then submit** — read `prior_events`, do the work, then call
   `relay_submit_turn(turn_token, body, next_baton=<the other agent>)`. Your `body` is
   your contribution; on the **first** turn, open by restating the `task` so the peer
   has the full brief (the thread does not store `task` separately).
   - To hand back for more discussion: `relay_submit_turn(..., next_baton=<other>)`
     (`status` is always `continue`; submit only ever hands the baton).
   - **To stop for a human, use `relay_halt_turn(turn_token, body, status="needs_human"`
     (or `"blocked"`), `question=...)`** — this records your turn AND pauses the thread in
     one atomic step, keeping the baton with you. The human answers (a resume), which
     reactivates the thread and wakes you again. Never put a halt through `relay_submit_turn`
     (it now rejects any non-continue status).

4. **Wait for the wake** — neither agent can wake the other. After you submit, the user
   (or a per-agent WS watcher) nudges the peer. When the baton returns to you, repeat
   from step 2. Always re-check with `relay_status(thread_id)` if unsure whose turn it is.

## Rules

- **Never** fabricate a `turn_token`; only use the one `relay_begin_turn` just returned.
- One `relay_begin_turn` per `relay_submit_turn`. Do not begin twice without submitting.
- `next_baton` must be a known agent id (`claude` or `codex`) — a typo strands the thread.
- Keep turns substantive and self-contained; the peer sees only what you write.
