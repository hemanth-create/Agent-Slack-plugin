"""Wake-driver: subscribes to the router /ws and drives one agent turn per wake.

One driver process per agent, single thread per driver (v0). The relay thread is the
agent's memory; the router stays the sole authority for baton/lease/idempotency.
"""
