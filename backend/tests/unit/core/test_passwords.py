"""Argon2id hashes and session tokens (docs/workflow.md 6.33.2, PR AU1)."""

import re

import pytest
from argon2 import extract_parameters

from app.core import passwords

PASSWORD = "correct horse battery"


def test_hash_is_argon2id_at_the_pinned_parameters_with_a_random_salt() -> None:
    first, second = passwords.hash_password(PASSWORD), passwords.hash_password(PASSWORD)

    assert first.startswith("$argon2id$")
    assert first != second
    parameters = extract_parameters(first)
    assert parameters.memory_cost >= 19 * 1024
    assert parameters.time_cost >= 2
    assert parameters.parallelism == 1
    assert (parameters.memory_cost, parameters.time_cost) == (19 * 1024, 2)
    assert PASSWORD not in first


def test_verify_accepts_only_the_exact_password() -> None:
    stored = passwords.hash_password(PASSWORD)

    assert passwords.verify_password(stored, PASSWORD)
    for wrong in (PASSWORD + " ", " " + PASSWORD, PASSWORD.upper(), PASSWORD[:-1], ""):
        assert not passwords.verify_password(stored, wrong)


def test_verify_never_raises_on_a_broken_or_missing_hash() -> None:
    assert not passwords.verify_password("!", PASSWORD)
    assert not passwords.verify_password("$argon2id$garbage", PASSWORD)
    assert not passwords.verify_password(None, PASSWORD)


@pytest.mark.parametrize(
    ("password", "ok"),
    [
        ("a" * 11, False),
        ("a" * 12, True),
        ("a" * 128, True),
        ("a" * 129, False),
        # Unicode characters, not bytes: 12 Thai characters are 36 UTF-8 bytes
        ("ก" * 12, True),
        ("ก" * 11, False),
        # Not trimmed: the spaces count
        ("   " + "a" * 9, True),
    ],
)
def test_length_is_12_to_128_characters_untrimmed(password: str, ok: bool) -> None:
    assert passwords.acceptable_password(password) is ok
    if ok:
        assert passwords.verify_password(passwords.hash_password(password), password)
    else:
        with pytest.raises(ValueError):
            passwords.hash_password(password)


def test_session_token_has_256_bits_and_only_its_sha256_is_stored() -> None:
    tokens = {passwords.new_session_token() for _ in range(50)}

    assert len(tokens) == 50
    token = tokens.pop()
    # token_urlsafe(32): 32 random bytes, 43 base64url characters
    assert len(token) >= 43
    digest = passwords.token_digest(token)
    assert re.fullmatch("[0-9a-f]{64}", digest)
    assert token not in digest
