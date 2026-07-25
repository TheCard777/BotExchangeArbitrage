"""Password hashing and session tokens (stdlib only — no extra dependency)."""
from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000
_ALGO = "sha256"


def hash_password(password: str) -> str:
    """Return 'salt$hash' using PBKDF2-HMAC-SHA256. A fresh random salt per user."""
    if not password:
        raise ValueError("Le mot de passe ne peut pas etre vide.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(_ALGO, password.encode(), salt.encode(), _ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a 'salt$hash' string, in constant time."""
    try:
        salt, expected = stored.split("$", 1)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac(_ALGO, password.encode(), salt.encode(), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected)


def new_token() -> str:
    """A random, URL-safe session token."""
    return secrets.token_urlsafe(32)
