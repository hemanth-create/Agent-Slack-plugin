from __future__ import annotations

import dataclasses

import pytest

from server.turn_token import TurnToken, decode, encode, mint


def test_mint_pins_ids_and_builds_a_key() -> None:
    tok = mint("t1", "lease-9", 7)
    assert tok.thread_id == "t1"
    assert tok.lease_id == "lease-9"
    assert tok.expected_last_turn_id == 7
    # The key embeds thread + expected id so a turn's idempotency is self-describing.
    assert tok.idempotency_key.startswith("t1:7:")


def test_mint_keys_are_unique_per_turn() -> None:
    a = mint("t1", "lease-1", 0)
    b = mint("t1", "lease-1", 0)
    assert a.idempotency_key != b.idempotency_key


def test_encode_decode_round_trips() -> None:
    tok = mint("thread-abc", "lease-xyz", 42)
    again = decode(encode(tok))
    assert again == tok


def test_decode_coerces_expected_id_to_int() -> None:
    # JSON numbers survive, but a token rebuilt from string data must still type-check.
    tok = TurnToken("t", "l", 3, "t:3:k")
    again = decode(encode(tok))
    assert isinstance(again.expected_last_turn_id, int)


def test_token_is_frozen() -> None:
    tok = mint("t1", "lease-1", 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        tok.thread_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["", "not-base64!!", "eyджунк", "YWJj"])
def test_decode_raises_value_error_on_garbage(bad: str) -> None:
    with pytest.raises(ValueError):
        decode(bad)
