from datetime import datetime, timedelta
from typing import Optional

from core.db import get_supabase
from core.security import decrypt_broker_credentials, encrypt_broker_credentials
from brokers import get_broker


class TokenManager:
    def __init__(self, user_id: str, broker: str):
        self.user_id = user_id
        self.broker = broker
        self._session: Optional[dict] = None

    async def get_session(self) -> dict:
        if self._session and self._is_valid():
            return self._session

        creds = await self._load_credentials()
        adapter_cls = get_broker(self.broker)
        adapter = adapter_cls()

        session = await adapter.authenticate(creds)
        self._session = {"access_token": session.access_token, "expires_at": session.expires_at}
        return self._session

    async def _load_credentials(self) -> dict:
        supabase = get_supabase()
        result = (
            supabase.table("broker_credentials")
            .select("*")
            .eq("user_id", self.user_id)
            .eq("broker", self.broker)
            .single()
            .execute()
        )
        if not result.data:
            raise ValueError(f"No credentials found for broker {self.broker}")

        row = result.data
        return {
            "client_id": decrypt_broker_credentials(row["encrypted_api_key"]),
            "secret_key": decrypt_broker_credentials(row["encrypted_secret_key"]),
            "access_token": decrypt_broker_credentials(row["encrypted_access_token"]) if row.get("encrypted_access_token") else "",
            **row.get("additional_params", {}),
        }

    async def save_access_token(self, token: str) -> None:
        supabase = get_supabase()
        encrypted = encrypt_broker_credentials(token)
        supabase.table("broker_credentials").update(
            {"encrypted_access_token": encrypted, "updated_at": datetime.utcnow().isoformat()}
        ).eq("user_id", self.user_id).eq("broker", self.broker).execute()

    def _is_valid(self) -> bool:
        if not self._session:
            return False
        expires = self._session.get("expires_at")
        if expires and datetime.utcnow() > expires - timedelta(minutes=5):
            return False
        return bool(self._session.get("access_token"))
