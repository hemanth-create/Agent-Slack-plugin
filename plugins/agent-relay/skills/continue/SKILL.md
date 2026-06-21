---
name: continue
description: Use when the user says it is your turn on an existing relay thread (the other agent just replied, or the user gives you a thread_id to join). Takes one turn and hands the baton back.
---

# Take your turn on a relay thread

The other agent has handed you the baton on a shared relay thread. Take exactly one turn.

## Steps

1. **Confirm it is your move** — call `relay_status(thread_id)`. Proceed only if
   `status == "active"` and `baton` is **you**. If the baton is the peer's, stop and tell
   the user it is not your turn yet.

2. **Claim the turn** — call `relay_begin_turn(thread_id)`. Read every entry in
   `prior_events` (the full conversation so far). Keep the returned `turn_token`.

3. **Respond** — do the actual work the thread calls for, then
   `relay_submit_turn(turn_token, body, next_baton=<the other agent>)`.
   - Engage with the peer's last turn directly: agree, refine, or disagree with reasons.
   - Hand back with `relay_submit_turn(..., next_baton=<other>)` to keep going.
   - To stop for a human instead, use `relay_halt_turn(turn_token, body,
     status="needs_human", question=...)` — it records your turn and pauses the thread
     atomically. `relay_submit_turn` rejects any non-continue status.

4. **Hand off** — after submitting, tell the user you have replied and the baton is now
   with the peer. Wait to be nudged again before taking another turn.

## Rules

- Exactly one `relay_begin_turn` → one `relay_submit_turn` per turn. Never submit with a
  token you did not just receive.
- `next_baton` must be `claude` or `codex` — never a typo, never yourself (that would
  loop the baton back to you and the peer would never wake).
- If `relay_begin_turn` raises `not_your_turn` or `baton_changed`, the situation moved
  under you — re-run `relay_status` and report to the user instead of forcing a write.
