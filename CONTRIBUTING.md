# Contributing to Agent-Slack

Contributions are welcome. This guide covers setup, the coding standards we enforce, and the
pull-request workflow.

## Local setup

Use Python 3.12+ on a **local, non-synced** folder (the router refuses to run a SQLite DB from a
OneDrive/Dropbox/iCloud path).

```bash
python -m venv venv
# Windows: venv\Scripts\activate   •   macOS/Linux: source venv/bin/activate
pip install -e ".[dev]"
pytest          # should be green
ruff check .    # should be clean
```

> On a synced checkout, run pytest against a non-synced temp dir so the router's sync-root
> guard doesn't trip: `pytest --basetemp="$TMPDIR/agent-slack"`.

## Coding standards

These are enforced from the first commit (full detail in [`AGENTS.md`](AGENTS.md)):

- **Files ≤ 150 LOC** (hard limit 200); **functions ≤ 15–20 LOC** (hard limit 20).
- **Type hints everywhere**; lint/format with `ruff` (config in `pyproject.toml`).
- **Pydantic** models for every request/response; no hand-mapped fields.
- **No raw SQL outside `router/db/`.** Route handlers stay thin; logic lives in service functions.
- **Names say exactly what they do** — one responsibility per file.
- **Every behavioral change ships with a pytest test.**

## Pull-request workflow

1. Fork and branch from `main` (`feature/...` or `fix/...`).
2. Make the change with tests. Keep diffs small and focused.
3. Run `ruff check . && pytest` locally — both must pass.
4. Open a PR using the template: what changed, why, and how you tested it.
5. CI (ruff + pytest on Windows/3.12) must be green before review.

## Architecture & scope

- Start with [`README.md`](README.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- `router/`, `plugins/agent-relay/`, and `wake_driver/` are the supported runtime.
  `experimental/` is unsupported — changes there are not gated by CI and carry no guarantees.

## Reporting bugs & security

- Bugs: open a GitHub issue using the bug-report template.
- Vulnerabilities: **do not** open a public issue — follow [`SECURITY.md`](SECURITY.md).
