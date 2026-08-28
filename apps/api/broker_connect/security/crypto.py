"""
Token encryption with key-rotation support.

Uses cryptography.fernet.MultiFernet:
  - The FIRST key in ENCRYPTION_KEYS is always used to ENCRYPT new tokens.
  - ALL keys are tried when DECRYPTING, so old ciphertext keeps working after
    you rotate. To rotate: prepend a fresh key, keep old ones for a grace
    period, then re-encrypt live rows and drop the retired key.

Generate a new key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

.env:
    ENCRYPTION_KEYS=<newest_key>,<older_key>,<oldest_key>
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet, InvalidToken


class TokenCryptoError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _cipher() -> MultiFernet:
    raw = os.environ.get("ENCRYPTION_KEYS", "").strip()
    if not raw:
        raise TokenCryptoError("ENCRYPTION_KEYS env var is empty.")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise TokenCryptoError("No usable keys in ENCRYPTION_KEYS.")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except Exception as exc:  # invalid key material
        raise TokenCryptoError(f"Invalid Fernet key in ENCRYPTION_KEYS: {exc}") from exc


def encrypt(plaintext: str) -> str:
    """Encrypt a token string. Returns Fernet ciphertext (str)."""
    if plaintext is None:
        raise TokenCryptoError("Cannot encrypt None.")
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a token string. Raises TokenCryptoError if no key matches."""
    if not ciphertext:
        raise TokenCryptoError("Empty ciphertext.")
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise TokenCryptoError("No encryption key could decrypt this token.") from exc


def rotate(ciphertext: str) -> str:
    """
    Re-encrypt existing ciphertext under the newest key without exposing
    plaintext. Use in a maintenance job after prepending a new key.
    """
    return _cipher().rotate(ciphertext.encode()).decode()
