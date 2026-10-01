from datetime import UTC, datetime

from application.interfaces.broker_oauth import EXECUTION, MARKET_DATA, ROLES, BrokerRepository
from core.audit import record_audit
from core.db import async_supabase, get_supabase
from core.models import AuditLogEntry
from core.safe_query import async_safe_execute, async_safe_single
from core.security import encrypt_broker_credentials
from domain.broker import BrokerCredential


def _check_role(role: str) -> str:
    """Refuse a role outside the known set, rather than matching no row.

    A bad role reaching `.eq("role", ...)` returns nothing, and "nothing" is exactly what
    a tenant with no credential also returns. Failing here makes the two distinguishable.
    """
    if role not in ROLES:
        raise ValueError(f"unknown credential role {role!r}; expected one of {ROLES}")
    return role


class SupabaseBrokerRepository(BrokerRepository):
    # ── reads ─────────────────────────────────────────────────────────────

    async def get_by_user_and_broker(self, user_id: str, broker: str, *, role: str = EXECUTION) -> BrokerCredential | None:
        rows = await async_safe_execute(
            get_supabase().table("broker_credentials")
            .select("id, user_id, broker, is_active, encrypted_api_key, encrypted_secret_key, role")
            .eq("user_id", user_id)
            .eq("broker", broker)
            .eq("role", _check_role(role))
        )
        if not rows:
            return None
        return BrokerCredential(**rows[0])

    async def get_by_user_and_broker_full(self, user_id: str, broker: str, *, role: str = EXECUTION) -> BrokerCredential | None:
        row = await async_safe_single(
            get_supabase().table("broker_credentials")
            .select("id, user_id, broker, is_active, encrypted_api_key, encrypted_secret_key, encrypted_access_token, additional_params, role")
            .eq("user_id", user_id)
            .eq("broker", broker)
            .eq("role", _check_role(role))
        )
        if not row:
            return None
        return BrokerCredential(**row)

    async def get_active_broker(self, user_id: str, *, role: str = EXECUTION) -> str | None:
        """The tenant's active broker for one role.

        Role-scoped, and that is the point of the whole change. Before this existed the
        query was `is_active = True` with `.limit(1)` and no ordering, which was safe only
        because a tenant could hold one row. Now a tenant can hold an execution and a
        market-data credential, and the unscoped query could hand back the market-data row
        to an *order* path — sending orders at a broker chosen for its prices.
        """
        row = await async_safe_single(
            get_supabase().table("broker_credentials")
            .select("broker")
            .eq("user_id", user_id)
            .eq("role", _check_role(role))
            .eq("is_active", True)
            .limit(1)
        )
        return row["broker"] if row else None

    async def resolve_market_data_broker(self, user_id: str) -> str | None:
        """The broker that should price this tenant's instruments.

        A market-data credential when the tenant has one, otherwise the execution broker.
        **The fallback is what makes this safe to roll out.** All 31 existing tenants have
        no market-data row, so every one of them resolves to exactly the broker it uses
        today — same credential, same adapter, same prices. Absence of a market-data row
        means "no separate choice has been made", never "no data available", which is the
        reading that would silently blank every existing tenant's quotes the day this
        shipped.
        """
        dedicated = await self.get_active_broker(user_id, role=MARKET_DATA)
        if dedicated:
            return dedicated
        return await self.get_active_broker(user_id, role=EXECUTION)

    # ── writes ────────────────────────────────────────────────────────────

    async def upsert_credentials(self, user_id: str, broker: str, api_key: str, secret_key: str, access_token: str | None = None, additional_params: dict | None = None, *, role: str = EXECUTION) -> BrokerCredential:
        _check_role(role)
        existing = await self.get_by_user_and_broker(user_id, broker, role=role)
        payload = {
            "encrypted_api_key": encrypt_broker_credentials(api_key),
            "encrypted_secret_key": encrypt_broker_credentials(secret_key),
            "additional_params": additional_params or {},
            "role": role,
        }
        if access_token is not None:
            payload["encrypted_access_token"] = encrypt_broker_credentials(access_token)

        supabase = get_supabase()
        if existing:
            result = await async_supabase(lambda: supabase.table("broker_credentials").update(payload).eq("id", existing.id).execute())
            inserted = result.data[0] if result.data else {"id": existing.id, "broker": broker, "is_active": existing.is_active, "role": role}
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
            details={"broker": broker, "role": role},
        ))
        return BrokerCredential(id=inserted.get("id", ""), user_id=user_id, broker=broker, is_active=inserted.get("is_active", False), encrypted_api_key="", encrypted_secret_key="", role=role)

    async def delete_credentials(self, user_id: str, broker: str, *, role: str = EXECUTION) -> bool:
        supabase = get_supabase()
        result = await async_supabase(lambda: supabase.table("broker_credentials").delete().eq("user_id", user_id).eq("broker", broker).eq("role", _check_role(role)).execute())
        success = bool(result and result.data)
        if success:
            record_audit(AuditLogEntry(
                user_id=user_id, action="remove_broker", resource="broker_credentials",
                resource_id="", details={"broker": broker, "role": role},
            ))
        return success

    async def list_credentials(self, user_id: str, *, role: str | None = None) -> list[dict]:
        """Credentials for a tenant, optionally narrowed to one role.

        `role=None` (the default, and what every existing caller means) returns every
        credential. Narrowing is opt-in so that adding a market-data row shows up in the
        existing `/brokers` page rather than silently disappearing from it — a page that
        lists fewer brokers than the tenant configured is its own bug report.
        """
        query = (
            get_supabase().table("broker_credentials")
            .select("id, broker, role, is_active, token_status, token_expires_at, created_at")
            .eq("user_id", user_id)
        )
        if role is not None:
            query = query.eq("role", _check_role(role))
        rows = await async_safe_execute(query)
        return rows or []

    async def activate_broker(self, user_id: str, broker: str, *, role: str = EXECUTION) -> bool:
        _check_role(role)
        supabase = get_supabase()
        target = await async_safe_single(
            supabase.table("broker_credentials")
            .select("id").eq("user_id", user_id).eq("broker", broker).eq("role", role)
        )
        if not target:
            return False

        # Scoped to this role. Unscoped, connecting a market-data broker would deactivate
        # the tenant's execution credential — so attaching a data feed would silently
        # stop their orders. That is the single most damaging thing this change could
        # regress, and it is the reason the deactivation is not simply left as it was.
        await async_supabase(lambda: supabase.table("broker_credentials").update({"is_active": False}).eq("user_id", user_id).eq("role", role).neq("broker", broker).execute())
        await async_supabase(lambda: supabase.table("broker_credentials").update({"is_active": True}).eq("id", target["id"]).execute())

        record_audit(AuditLogEntry(
            user_id=user_id, action="activate_broker", resource="broker_credentials",
            resource_id=target["id"], details={"broker": broker, "role": role},
        ))
        return True

    async def update_access_token(self, credential_id: str, access_token: str, refresh_token: str | None = None) -> None:
        payload: dict = {
            "encrypted_access_token": encrypt_broker_credentials(access_token),
            "is_active": True,
            "token_status": "valid",
            "last_token_refresh_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        expires_at = self._decode_jwt_expiry(access_token)
        if expires_at:
            payload["token_expires_at"] = expires_at
        if refresh_token:
            payload["encrypted_refresh_token"] = encrypt_broker_credentials(refresh_token)
        await async_supabase(lambda: get_supabase().table("broker_credentials").update(payload).eq("id", credential_id).execute())

    @staticmethod
    def _decode_jwt_expiry(access_token: str) -> str | None:
        try:
            import base64
            import json
            parts = access_token.split(".")
            if len(parts) != 3:
                return None
            padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            exp = payload.get("exp")
            if not exp:
                return None
            from datetime import timezone
            return datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
        except Exception:
            return None

    async def clear_access_token(self, credential_id: str) -> None:
        await async_supabase(lambda: get_supabase().table("broker_credentials").update(
            {"is_active": False, "encrypted_access_token": ""}
        ).eq("id", credential_id).execute())
