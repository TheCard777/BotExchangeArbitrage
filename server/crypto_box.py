"""Encryption of users' exchange API keys at rest.

Storing other people's exchange API keys is the most sensitive part of the
platform: a leak means their funds are at risk. So keys are NEVER stored in
clear text — they are encrypted with Fernet (AES-128-CBC + HMAC) using a master
secret that lives only in an environment variable (BOT_PLATFORM_SECRET), never
in the database or the code.

Generate a master secret once and keep it safe (a secrets manager in prod):

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

_ENV_VAR = "BOT_PLATFORM_SECRET"


class SecretConfigError(RuntimeError):
    pass


def _fernet() -> Fernet:
    secret = os.environ.get(_ENV_VAR)
    if not secret:
        raise SecretConfigError(
            f"{_ENV_VAR} is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and set it in the environment. "
            "Never commit it."
        )
    try:
        return Fernet(secret.encode() if isinstance(secret, str) else secret)
    except Exception as e:  # malformed key
        raise SecretConfigError(f"{_ENV_VAR} is not a valid Fernet key: {e}") from None


def encrypt(plaintext: str) -> str:
    """Encrypt a secret (e.g. an API key) to a storable string. Empty stays empty."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a stored value. Empty stays empty; tampered/invalid data raises."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise SecretConfigError(
            "Impossible de dechiffrer une cle API (secret different ou donnee alteree)."
        ) from None
