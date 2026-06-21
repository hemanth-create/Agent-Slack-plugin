"""Tests for router.config.credentials: generate, persist, load, reverse map, harden."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from router.config.credentials import (
    AgentTokens,
    generate,
    harden,
    load_tokens,
    reverse_map,
    write_tokens,
)


def test_generate_one_token_per_agent() -> None:
    tokens = generate(("claude", "codex"))
    assert set(tokens.agents) == {"claude", "codex"}
    assert tokens.agents["claude"] != tokens.agents["codex"]


def test_tokens_are_high_entropy() -> None:
    tokens = generate(("claude",))
    assert len(tokens.agents["claude"]) >= 32


def test_write_then_load_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    original = generate(("claude", "codex"))
    write_tokens(path, original)
    assert load_tokens(path).agents == original.agents


def test_reverse_map_inverts() -> None:
    tokens = generate(("claude", "codex"))
    rmap = reverse_map(tokens)
    assert rmap[tokens.agents["claude"]] == "claude"
    assert rmap[tokens.agents["codex"]] == "codex"


def test_harden_warns_on_windows_else_applies(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    write_tokens(path, generate(("claude",)))
    result = harden(path)
    if os.name == "posix":
        assert result is None
    else:
        assert isinstance(result, str) and result


def test_rejects_duplicate_tokens() -> None:
    with pytest.raises(ValidationError):
        AgentTokens(agents={"claude": "z" * 40, "codex": "z" * 40})


def test_rejects_unknown_version() -> None:
    with pytest.raises(ValidationError):
        AgentTokens(version=2, agents={"claude": "a" * 40, "codex": "b" * 40})


def test_rejects_weak_token() -> None:
    with pytest.raises(ValidationError):
        AgentTokens(agents={"claude": "short", "codex": "x" * 40})


def test_rejects_whitespace_token() -> None:
    with pytest.raises(ValidationError):
        AgentTokens(agents={"claude": " " + "x" * 40, "codex": "y" * 40})
