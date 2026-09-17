import logging
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from core.config import settings

logger = logging.getLogger(__name__)

_ph = PasswordHasher()

if len(settings.encryption_key) != 44:
    raise ValueError(
        f"ENCRYPTION_KEY must be a 44-character base64 Fernet key (got {len(settings.encryption_key)} chars). "
        "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )
_fernet = Fernet(settings.encryption_key.encode())
_old_fernets: list[Fernet] | None = None


def _get_old_fernets() -> list[Fernet]:
    """Return Fernet instances for any old/rotated encryption keys.

    Supports gradual key rotation: new credentials are encrypted with the primary
    ENCRYPTION_KEY; old credentials encrypted with previously-active keys can still
    be decrypted.  Old keys are read from the ENCRYPTION_KEYS env var (comma-separated
    base64 Fernet keys).
    """
    global _old_fernets
    if _old_fernets is not None:
        return _old_fernets
    raw = getattr(settings, "encryption_keys", "") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    _old_fernets = [Fernet(k.encode()) for k in keys if len(k) == 44]
    return _old_fernets


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, password)
    except Exception:
        return False


def encrypt_broker_credentials(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_broker_credentials(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    # Try primary key first
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        pass
    # Fall back to old/rotated keys
    for old_fernet in _get_old_fernets():
        try:
            return old_fernet.decrypt(ciphertext.encode()).decode()
        except Exception:
            continue
    logger.error("Failed to decrypt broker credentials with primary and all old keys")
    raise ValueError("Cannot decrypt broker credentials — key rotation may be incomplete")


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (expires_delta or timedelta(hours=24))
    to_encode = {"sub": subject, "exp": expire, "iat": datetime.now(UTC)}
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload
    except JWTError:
        return None
