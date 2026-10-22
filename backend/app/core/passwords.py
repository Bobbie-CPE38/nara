"""Password hashing and session tokens (docs/workflow.md 6.33.2).

Argon2id with the library's random salt, at the OWASP Password Storage minimum
(19 MiB memory, 2 iterations, 1 lane). The parameters are pinned here, not taken from
argon2-cffi's defaults, so a library upgrade cannot change them silently; a test
checks the encoded hash. A password is never stored, returned or logged.
"""

import hashlib
import secrets

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
ARGON2_MEMORY_KIB = 19 * 1024
ARGON2_ITERATIONS = 2
ARGON2_PARALLELISM = 1

_hasher = PasswordHasher(
    time_cost=ARGON2_ITERATIONS,
    memory_cost=ARGON2_MEMORY_KIB,
    parallelism=ARGON2_PARALLELISM,
    type=Type.ID,
)
# Verified when there is no account, so a missing account costs the same time as a
# wrong password. Hashed once at import from a random value nobody knows
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))

# 32 bytes = 256 bits of randomness
SESSION_TOKEN_BYTES = 32


def acceptable_password(password: str) -> bool:
    """12 to 128 Unicode characters, counted as they arrive: no trimming, no cutting."""
    return PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH


def hash_password(password: str) -> str:
    if not acceptable_password(password):
        raise ValueError(
            f"password must be {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters"
        )
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True only for the right password. Never raises for a wrong or broken hash.

    With no hash (no usable account) a dummy hash is still verified, so the answer
    takes about as long either way.
    """
    try:
        if password_hash is None:
            _hasher.verify(_DUMMY_HASH, password)
            return False
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def token_digest(token: str) -> str:
    """Lowercase hex SHA-256: the only form of a session token the database holds."""
    return hashlib.sha256(token.encode()).hexdigest()
