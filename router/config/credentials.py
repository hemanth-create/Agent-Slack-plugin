"""Per-agent bearer credentials: generate, persist to data/secrets.json, load."""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from pydantic import BaseModel, model_validator

DEFAULT_AGENTS: tuple[str, ...] = ("claude", "codex")
SECRETS_VERSION = 1
_TOKEN_BYTES = 32
_MIN_TOKEN_LEN = 32


class AgentTokens(BaseModel):
    """The secrets.json shape: schema version + {agent_id: bearer_token}."""

    version: int = SECRETS_VERSION
    agents: dict[str, str]

    @model_validator(mode="after")
    def _check(self) -> "AgentTokens":
        """Fail closed on an unsupported version, duplicate tokens, or weak tokens."""
        if self.version != SECRETS_VERSION:
            raise ValueError(
                f"unsupported secrets version {self.version}; expected {SECRETS_VERSION}"
            )
        if len(set(self.agents.values())) != len(self.agents):
            raise ValueError("duplicate tokens: each agent needs a distinct token")
        for agent, token in self.agents.items():
            if token != token.strip() or len(token) < _MIN_TOKEN_LEN:
                raise ValueError(
                    f"token for {agent!r} must be whitespace-free and >= {_MIN_TOKEN_LEN} chars"
                )
        return self


def generate(agent_ids: tuple[str, ...] = DEFAULT_AGENTS) -> AgentTokens:
    """Mint one opaque high-entropy token per agent id."""
    return AgentTokens(agents={a: secrets.token_urlsafe(_TOKEN_BYTES) for a in agent_ids})


def write_tokens(path: Path, tokens: AgentTokens) -> None:
    """Persist credentials as JSON (caller ensures the dir exists and is gitignored)."""
    path.write_text(tokens.model_dump_json(indent=2), encoding="utf-8")


def load_tokens(path: Path) -> AgentTokens:
    """Load and validate the secrets file."""
    return AgentTokens.model_validate_json(path.read_text(encoding="utf-8"))


def reverse_map(tokens: AgentTokens) -> dict[str, str]:
    """Build the token -> agent_id lookup the auth layer resolves against."""
    return {token: agent for agent, token in tokens.agents.items()}


def harden(path: Path) -> str | None:
    """Best-effort restrict the secrets file to its owner.

    POSIX: apply 0600 and return None. This is post-write, so umask governs the brief
    window before chmod (an up-front os.open(0o600) is a noted hardening backlog item).
    Non-POSIX (Windows): stdlib cannot set real ACLs, so return an explicit warning
    instead of pretending 0600 semantics exist.
    """
    if os.name == "posix":
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        return None
    return (
        f"{path.name} is not OS-hardened on this platform; it relies on the gitignored "
        "data/ dir and your user-profile ACLs (no POSIX 0600 enforcement here)."
    )
