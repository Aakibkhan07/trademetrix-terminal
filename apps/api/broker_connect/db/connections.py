"""
Broker token vault — ALIGNED to your existing `broker_credentials` table.

Your schema already has the vault:
  broker_credentials(user_id, broker, encrypted_access_token, encrypted_api_key,
                     encrypted_secret_key, additional_params jsonb, is_active,
                     token_status, token_expires_at, last_token_refresh_at, ...)

So we do NOT create a new table. We read/write broker_credentials. Refresh token
and the broker's user id ride inside additional_params (refresh encrypted).

Redis still holds the short-lived OAuth `state` (CSRF) during the redirect.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from functools import lru_cache

import redis.asyncio as aioredis
from supabase import create_client, Client

from ..config import get_settings
from ..security.crypto import encrypt, decrypt
from ..brokers.base import BrokerToken

TABLE = "broker_credentials"          # <-- your existing vault
_STATE_PREFIX = "oauth_state:"


@lru_cache(maxsize=1)
def _sb() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_key)


@lru_cache(maxsize=1)
def _redis() -> aioredis.Redis:
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


# --- OAuth state (CSRF) ----------------------------------------------------
async def issue_state(user_id: str, broker: str) -> str:
    state = secrets.token_urlsafe(32)
    await _redis().set(
        f"{_STATE_PREFIX}{state}",
        json.dumps({"user_id": user_id, "broker": broker}),
        ex=get_settings().oauth_state_ttl,
    )
    return state


async def consume_state(state: str) -> dict | None:
    key = f"{_STATE_PREFIX}{state}"
    r = _redis()
    payload = await r.get(key)
    if not payload:
        return None
    await r.delete(key)
    return json.loads(payload)


# --- token vault (broker_credentials) --------------------------------------
def upsert_connection(user_id: str, broker: str, token: BrokerToken) -> dict:
    extra = {"broker_user_id": token.broker_user_id}
    if token.refresh_token:
        extra["refresh_token_enc"] = encrypt(token.refresh_token)
    if token.extra:
        # Persist broker-specific extras (e.g. Kotak Neo base_url/sid/consumer_key)
        # so daily re-auth has what it needs without re-entering everything.
        extra.update({k: v for k, v in token.extra.items() if v is not None})

    row = {
        "user_id": user_id,
        "broker": broker,
        "encrypted_access_token": encrypt(token.access_token),
        "additional_params": extra,
        "is_active": True,
        "token_status": "valid",   # matches your existing vocab (valid / needs_attention / revoked)
        "token_expires_at": token.expires_at.isoformat(),
        "last_token_refresh_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Persist a broker "api key" (Kotak Neo consumer_key) so client_id stays
    # populated for the execution engine even though we authenticate with the
    # trade token + sid rather than an OAuth client secret.
    if token.extra:
        api_key = token.extra.get("api_key") or token.extra.get("consumer_key")
        if api_key:
            row["encrypted_api_key"] = encrypt(api_key)
    # Requires a unique/constraint on (user_id, broker). If your table allows
    # multiple creds per broker, change on_conflict to your PK or add the
    # constraint. See INTEGRATION.md.
    res = _sb().table(TABLE).upsert(row, on_conflict="user_id,broker").execute()
    return res.data[0] if res.data else row


def get_decrypted_token(user_id: str, broker: str) -> dict | None:
    """Execution-engine only. Returns plaintext token + expiry, or None."""
    res = (
        _sb()
        .table(TABLE)
        .select("encrypted_access_token, additional_params, broker, token_status, token_expires_at")
        .eq("user_id", user_id)
        .eq("broker", broker)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    r = res.data[0]
    extra = r.get("additional_params") or {}
    refresh_enc = extra.get("refresh_token_enc")
    return {
        "access_token": decrypt(r["encrypted_access_token"]),
        "refresh_token": decrypt(refresh_enc) if refresh_enc else None,
        "broker_user_id": extra.get("broker_user_id"),
        "token_expires_at": r["token_expires_at"],
        "extra": {k: v for k, v in extra.items() if k not in ("broker_user_id", "refresh_token_enc")},
        # normalise your token_status values to the engine's expected word
        "status": "connected" if r.get("token_status") in ("connected", "active", "valid") else (r.get("token_status") or "unknown"),
    }


def mark_status(user_id: str, broker: str, status: str, error: str | None = None) -> None:
    patch = {"token_status": status}
    if error:
        patch["additional_params"] = {"last_error": error}
    _sb().table(TABLE).update(patch).eq("user_id", user_id).eq("broker", broker).execute()


def disconnect(user_id: str, broker: str) -> None:
    # soft-revoke: flip is_active off (keeps history) instead of deleting
    _sb().table(TABLE).update(
        {"is_active": False, "token_status": "revoked"}
    ).eq("user_id", user_id).eq("broker", broker).execute()


def list_status(user_id: str) -> list[dict]:
    """Ciphertext-free status for the portal (reads the view from migration 002)."""
    res = (
        _sb()
        .table("broker_connection_status")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return res.data or []
