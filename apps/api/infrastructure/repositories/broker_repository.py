from datetime import UTC, datetime

from application.interfaces.broker_oauth import BrokerRepository
from core.audit import record_audit
from core.db import async_supabase, get_supabase
from core.models import AuditLogEntry
from core.safe_query import async_safe_execute, async_safe_single
from core.security import encrypt_broker_credentials
from domain.broker import BrokerCredential


class SupabaseBrokerRepository(BrokerRepository):
    async def get_by_user_and_broker(self, user_id: str, broker: str) -> BrokerCredential | None:
        rows = await async_safe_execute(
            get_supabase().table("broker_credentials")
            .select("id, user_id, broker, is_active, encrypted_api_key, encrypted_secret_key")
            .eq("user_id", user_id)
            .eq("broker", broker)
        )
        if not rows:
            return None
        return BrokerCredential(**rows[0])

    async def get_by_user_and_broker_full(self, user_id: str, broker: str) -> BrokerCredential | None:
        row = await async_safe_single(
            get_supabase().table("broker_credentials")
            .select("id, user_id, broker, is_active, encrypted_api_key, encrypted_secret_key, encrypted_access_token, additional_params")
            .eq("user_id", user_id)
            .eq("broker", broker)
        )
        if not row:
            return None
        return BrokerCredential(**row)

    async def upsert_credentials(self, user_id: str, broker: str, api_key: str, secret_key: str, access_token: str | None = None, additional_params: dict | None = None) -> BrokerCredential:
        existing = await self.get_by_user_and_broker(user_id, broker)
        payload = {
            "encrypted_api_key": encrypt_broker_credentials(api_key),
            "encrypted_secret_key": encrypt_broker_credentials(secret_key),
            "additional_params": additional_params or {},
        }
        if access_token is not None:
            payload["encrypted_access_token"] = encrypt_broker_credentials(access_token)

        supabase = get_supabase()
        if existing:
            result = await async_supabase(lambda: supabase.table("broker_credentials").update(payload).eq("id", existing.id).execute())
            inserted = result.data[0] if result.data else {"id": existing.id, "broker": broker, "is_active": existing.is_active}
        else:
            payload["user_id"] = user_id
            payload["broker"] = broker
            result = await async_supabase(lambda: supabase.table("broker_credentials").insert(payload).execute())
            inserted = result.data[0]

        record_audit(AuditLogEntry(
            user_id=user_id,
            action="update_broker" if existing else "add_broker",
            resource="broker_credentials",
            resource_id=inserted.get("id", ""),
            details={"broker": broker},
        ))
        return BrokerCredential(id=inserted.get("id", ""), user_id=user_id, broker=broker, is_active=inserted.get("is_active", False), encrypted_api_key="", encrypted_secret_key="")

    async def delete_credentials(self, user_id: str, broker: str) -> bool:
        supabase = get_supabase()
        result = await async_supabase(lambda: supabase.table("broker_credentials").delete().eq("user_id", user_id).eq("broker", broker).execute())
        success = bool(result and result.data)
        if success:
            record_audit(AuditLogEntry(
                user_id=user_id, action="remove_broker", resource="broker_credentials",
                resource_id="", details={"broker": broker},
            ))
        return success

    async def list_credentials(self, user_id: str) -> list[dict]:
        rows = await async_safe_execute(
            get_supabase().table("broker_credentials")
            .select("id, broker, is_active, created_at")
            .eq("user_id", user_id)
        )
        return rows or []

    async def activate_broker(self, user_id: str, broker: str) -> bool:
        supabase = get_supabase()
        target = await async_safe_single(
            supabase.table("broker_credentials")
            .select("id").eq("user_id", user_id).eq("broker", broker)
        )
        if not target:
            return False

        await async_supabase(lambda: supabase.table("broker_credentials").update({"is_active": False}).eq("user_id", user_id).neq("broker", broker).execute())
        await async_supabase(lambda: supabase.table("broker_credentials").update({"is_active": True}).eq("id", target["id"]).execute())

        record_audit(AuditLogEntry(
            user_id=user_id, action="activate_broker", resource="broker_credentials",
            resource_id=target["id"], details={"broker": broker},
        ))
        return True

    async def update_access_token(self, credential_id: str, access_token: str, refresh_token: str | None = None) -> None:
        payload: dict = {
            "encrypted_access_token": encrypt_broker_credentials(access_token),
            "is_active": True,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if refresh_token:
            payload["encrypted_refresh_token"] = encrypt_broker_credentials(refresh_token)
        await async_supabase(lambda: get_supabase().table("broker_credentials").update(payload).eq("id", credential_id).execute())

    async def clear_access_token(self, credential_id: str) -> None:
        await async_supabase(lambda: get_supabase().table("broker_credentials").update(
            {"is_active": False, "encrypted_access_token": ""}
        ).eq("id", credential_id).execute())
