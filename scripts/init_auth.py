"""Generate data/secrets.json with one bearer token per agent (run once)."""
from __future__ import annotations

from router.config.credentials import DEFAULT_AGENTS, generate, harden, write_tokens
from router.paths import SECRETS_PATH, ensure_data_dir


def main() -> None:
    """Mint per-agent tokens and write the gitignored secrets file."""
    ensure_data_dir()
    if SECRETS_PATH.exists():
        print(f"{SECRETS_PATH} already exists; refusing to overwrite.")
        return
    write_tokens(SECRETS_PATH, generate(DEFAULT_AGENTS))
    warning = harden(SECRETS_PATH)
    print(f"Wrote {SECRETS_PATH} with tokens for: {', '.join(DEFAULT_AGENTS)}.")
    if warning:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
