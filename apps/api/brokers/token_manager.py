import asyncio
import logging
from datetime import UTC, datetime, timedelta

from cryptography.fernet import InvalidToken

from brokers import get_broker
from core.db import async_supabase, get_supabase
from core.security import decrypt_broker_credentials, encrypt_broker_credentials

logger = logging.getLogger(__name__)

TOKEN_REFRESH_TIMEOUT = 10.0
TOKEN_REFRESH_MAX_RETRIES = 1
TOKEN_REFRESH_BASE_DELAY = 1.0
TOKEN_EXPIRY_BUFFER_MINUTES = 5


class TokenManager:
    _locks: dict[str, asyncio.Lock] = {}
    _lock_lock = asyncio.Lock()

    def __init__(self, user_id: str, broker: str):
        self.user_id = user_id
        self.broker = broker
        self._lock_key = f"{user_id}:{broker}"
        self._session: dict | None = None
        self._refresh_in_progress = False

    async def get_session(self) -> dict:
        if self._session and self._is_valid():
            return self._session

        lock = await self._get_lock()
        async with lock:
            if self._session and self._is_valid():
                return self._session
            if self._refresh_in_progress:
                raise RuntimeError(f"Token refresh already in progress for {self._lock_key}")

            self._refresh_in_progress = True
            try:
                await self._refresh()
                return self._session
            finally:
                self._refresh_in_progress = False

    async def _refresh(self) -> None:
        creds = await self._load_credentials()
        adapter_cls = get_broker(self.broker)
        adapter = adapter_cls()

        for attempt in range(TOKEN_REFRESH_MAX_RETRIES + 1):
            try:
                session_obj = await asyncio.wait_for(
                    adapter.authenticate(creds),
                    timeout=TOKEN_REFRESH_TIMEOUT,
                )
                access_token = session_obj.access_token if hasattr(session_obj, "access_token") else session_obj.get("access_token", "")
                expires_at = session_obj.expires_at if hasattr(session_obj, "expires_at") else session_obj.get("expires_at")

                if not access_token:
                    raise ValueError("Empty access token returned by broker")

                self._session = {"access_token": access_token, "expires_at": expires_at}
                await self.save_access_token(access_token, expires_at)
                logger.info("Token refreshed for %s (attempt %d)", self._lock_key, attempt + 1)
                return

            except asyncio.TimeoutError:
                logger.warning("Token refresh timeout for %s (attempt %d/%d)", self._lock_key, attempt + 1, TOKEN_REFRESH_MAX_RETRIES)
                if attempt < TOKEN_REFRESH_MAX_RETRIES:
                    await asyncio.sleep(TOKEN_REFRESH_BASE_DELAY * (2 ** attempt))
                else:
                    raise RuntimeError(f"Token refresh timed out for {self._lock_key} after {TOKEN_REFRESH_MAX_RETRIES} retries")

            except Exception as e:
                logger.warning("Token refresh failed for %s (attempt %d/%d): %s", self._lock_key, attempt + 1, TOKEN_REFRESH_MAX_RETRIES, e)
                if attempt < TOKEN_REFRESH_MAX_RETRIES:
                    await asyncio.sleep(TOKEN_REFRESH_BASE_DELAY * (2 ** attempt))
                else:
                    raise RuntimeError(f"Token refresh failed for {self._lock_key}: {e}") from e

    async def _load_credentials(self) -> dict:
        supabase = get_supabase()
        try:
            result = await async_supabase(lambda: supabase.table("broker_credentials").select("*").eq("user_id", self.user_id).eq("broker", self.broker).order("created_at", desc=True).limit(1).execute())
            if not result.data:
                raise ValueError(f"No credentials found for broker {self.broker}")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to load credentials for broker {self.broker}: {e}")

        for row in result.data:
            try:
                return {
                    "client_id": decrypt_broker_credentials(row["encrypted_api_key"]),
                    "secret_key": decrypt_broker_credentials(row["encrypted_secret_key"]),
                    "access_token": decrypt_broker_credentials(row.get("encrypted_access_token", "")) if row.get("encrypted_access_token") else "",
                    **row.get("additional_params", {}),
                }
            except InvalidToken:
                logger.warning("Skipping credential %s with invalid encryption (key rotation)", row.get("id", "unknown"))
                continue
        raise ValueError(f"No decryptable credentials found for broker {self.broker} (key may have been rotated)")

    async def save_access_token(self, token: str, expires_at=None) -> None:
        supabase = get_supabase()
        encrypted = encrypt_broker_credentials(token)
        update_data = {
            "encrypted_access_token": encrypted,
            "token_status": "valid",
            "last_token_refresh_at": datetime.now(UTC).isoformat(),
        }
        if expires_at:
            expiry = expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)
            update_data["token_expires_at"] = expiry
        try:
            await async_supabase(lambda: supabase.table("broker_credentials").update(
                update_data
            ).eq("user_id", self.user_id).eq("broker", self.broker).execute())
        except Exception as e:
            logger.warning("Failed to save access token: %s", e)

    def invalidate_session(self) -> None:
        self._session = None

    def _is_valid(self) -> bool:
        if not self._session:
            return False
        expires = self._session.get("expires_at")
        if expires:
            try:
                expiry_dt = expires if isinstance(expires, datetime) else datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                if datetime.now(UTC) > expiry_dt - timedelta(minutes=TOKEN_EXPIRY_BUFFER_MINUTES):
                    return False
            except (ValueError, TypeError):
                return False
        return bool(self._session.get("access_token"))

    async def _get_lock(self) -> asyncio.Lock:
        async with self._lock_lock:
            if self._lock_key not in self._locks:
                self._locks[self._lock_key] = asyncio.Lock()
            return self._locks[self._lock_key]
