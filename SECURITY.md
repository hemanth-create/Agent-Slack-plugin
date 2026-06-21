# Security Policy

## Reporting a vulnerability

**Please do not report security issues in public GitHub issues.**

Report privately through GitHub's **[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)**:
open the repository's **Security** tab → **Report a vulnerability**. This opens a private advisory
visible only to the maintainers.

Please include: a description, steps to reproduce, affected component (e.g. router auth, baton/lease
logic, path/scope checks, idempotency), and the impact you observed.

## Response

This is a small open-source project maintained on a best-effort basis. We aim to acknowledge a
report within a few days and will coordinate a fix and disclosure timeline with you. There is no
paid bug-bounty program.

## Scope

Agent-Slack is **local-only by design** — the router binds to loopback and there is no cloud
service. The most relevant areas:

- **In scope:** authentication (bearer tokens, agent derivation), the accept transaction
  (baton / lease / idempotency / optimistic-concurrency gates), WebSocket `Origin` validation,
  and path/scope canonicalization.
- **Out of scope:** how *you* store your own tokens, third-party dependency CVEs (report those
  upstream), and running the router on a network interface other than loopback (unsupported).

## Handling secrets

Bearer tokens live in `data/secrets.json`, which is gitignored and must never be committed.
Committed config files and examples use placeholders only.
