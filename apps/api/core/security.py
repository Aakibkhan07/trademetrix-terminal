from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from core.config import settings

_ph = PasswordHasher()
_fernet = Fernet(settings.encryption_key.encode() if len(settings.encryption_key) == 44 else Fernet.generate_key())


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except Exception:
        return False


def encrypt_broker_credentials(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_broker_credentials(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


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
