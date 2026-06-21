-- Local Multi-Agent Relay Router - v0 schema.
-- router.db is the sole authority; thread.md / state.json are generated projections.
-- All SQL for the router lives under router/db/. The runtime DB is created at data/router.db.

CREATE TABLE IF NOT EXISTS threads (
    thread_id     TEXT PRIMARY KEY,
    status        TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'needs_human', 'blocked', 'done', 'cancelled')),
    status_reason TEXT
                    CHECK (status_reason IS NULL OR status_reason IN (
                        'recovery_required', 'disconnected', 'invalid_submission',
                        'stale_read', 'auth_failure', 'user_cancelled',
                        'projection_error', 'port_conflict')),
    baton         TEXT,
    last_turn_id  INTEGER NOT NULL DEFAULT 0,
    workspace_id  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    -- A halt state must record why; clean operational states must not carry a reason.
    -- This makes status_reason a true discriminator (closes the ambiguous needs_human gap).
    CHECK (
        (status IN ('active', 'done') AND status_reason IS NULL)
        OR (status IN ('needs_human', 'blocked', 'cancelled') AND status_reason IS NOT NULL)
    )
);

-- Server-assigned, monotonic turn ids. turns also serves as the GET /events?since= stream.
-- payload_hash makes the turn ledger tamper-evident and backs idempotency replay detection.
-- reply_to is a composite self-FK: a turn can only reply to another turn in the SAME thread
-- (MATCH SIMPLE -- a NULL reply_to means "replies to nothing" and is left unchecked).
CREATE TABLE IF NOT EXISTS turns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id    TEXT NOT NULL REFERENCES threads(thread_id),
    author       TEXT NOT NULL,
    reply_to     INTEGER,
    ts           TEXT NOT NULL,
    body         TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    FOREIGN KEY (thread_id, reply_to) REFERENCES turns(thread_id, id)
);
-- UNIQUE so (thread_id, id) can serve as the composite-FK target (above and in idempotency).
CREATE UNIQUE INDEX IF NOT EXISTS idx_turns_thread ON turns(thread_id, id);

CREATE TABLE IF NOT EXISTS leases (
    lease_id     TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL REFERENCES threads(thread_id),
    agent        TEXT NOT NULL,
    acquired_at  TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    heartbeat_at TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'expired', 'released'))
);
CREATE INDEX IF NOT EXISTS idx_leases_thread ON leases(thread_id);

-- Per-agent read cursor (last_processed_id).
CREATE TABLE IF NOT EXISTS participants (
    thread_id         TEXT NOT NULL REFERENCES threads(thread_id),
    agent             TEXT NOT NULL,
    last_processed_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (thread_id, agent)
);

-- Idempotency: the PRIMARY KEY enforces UNIQUE(thread_id, auth_agent, idempotency_key).
-- stored_turn_id is NOT NULL: a cache row is only written after its turn is appended
-- (accept-transaction order), so there is no valid row without a stored turn in v0.
-- The composite FK (both columns NOT NULL) guarantees the cached turn is in this same thread.
CREATE TABLE IF NOT EXISTS idempotency (
    thread_id       TEXT NOT NULL REFERENCES threads(thread_id),
    auth_agent      TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_hash    TEXT NOT NULL,
    stored_turn_id  INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (thread_id, auth_agent, idempotency_key),
    FOREIGN KEY (thread_id, stored_turn_id) REFERENCES turns(thread_id, id)
);

CREATE TABLE IF NOT EXISTS projections_dirty (
    thread_id             TEXT PRIMARY KEY REFERENCES threads(thread_id),
    dirty                 INTEGER NOT NULL DEFAULT 0,
    last_rendered_turn_id INTEGER NOT NULL DEFAULT 0
);
