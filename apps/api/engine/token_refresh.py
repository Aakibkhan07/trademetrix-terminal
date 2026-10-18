"""
Broker token refresh job.

Refreshes expired access tokens for all connected users before market open.
Fyers (and some other brokers) issue tokens that expire daily.

Usage (cron):
  30 8 * * 1-5 cd /app && python -m engine.token_refresh  # 8:30 AM IST Mon-Fri

Or call refresh_all_tokens() directly from the scheduler.

This script does NOT enable or install cron — that is the operator's responsibility.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from brokers import create_broker
from core.db import get_supabase
from core.safe_query import async_safe_execute, async_safe_update
from core.security import decrypt_broker_credentials, encrypt_broker_credentials

logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


async def refresh_user_token(user_id: str, broker: str, creds: dict) -> dict:
    """Attempt to refresh a single user's broker token. Returns status dict."""
    try:
        adapter = create_broker(broker)
        session = await adapter.authenticate(creds)

        now = datetime.now(UTC)
        result = {
            "user_id": user_id,
            "broker": broker,
            "success": True,
            "has_token": bool(session.access_token),
        }

        supabase = get_supabase()
        update_data = {
            "token_status": "valid",
            "last_token_refresh_at": now.isoformat(),
        }
        if session.expires_at:
            update_data["token_expires_at"] = session.expires_at.isoformat()

        if session.access_token:
            encrypted = encrypt_broker_credentials(session.access_token)
            update_data["encrypted_access_token"] = encrypted

        await async_safe_update("broker_credentials", update_data, "user_id", user_id, match_value2=broker, match_field2="broker")
        logger.info("Token refreshed: user=%s broker=%s", user_id, broker)
        return result

    except Exception as e:
        logger.warning("Token refresh failed: user=%s broker=%s error=%s", user_id, broker, e)
        await async_safe_update("broker_credentials", {"token_status": "needs_attention"}, "user_id", user_id, match_value2=broker, match_field2="broker")
        return {
            "user_id": user_id,
            "broker": broker,
            "success": False,
            "error": str(e),
        }


async def refresh_all_tokens() -> list[dict]:
    """Iterate all active broker credentials and refresh tokens."""
    supabase = get_supabase()
    rows = await async_safe_execute(
        supabase.table("broker_credentials")
        .select("*")
        .eq("is_active", True)
    )
    if not rows:
        logger.info("No active broker credentials to refresh")
        return []

    results = []
    for row in rows:
        try:
            client_id = decrypt_broker_credentials(row["encrypted_api_key"]) if row.get("encrypted_api_key") else ""
            secret_key = decrypt_broker_credentials(row["encrypted_secret_key"]) if row.get("encrypted_secret_key") else ""
            existing_token = decrypt_broker_credentials(row["encrypted_access_token"]) if row.get("encrypted_access_token") else ""
        except Exception as e:
            logger.warning("Skipping user=%s broker=%s: cannot decrypt credentials (%s)", row["user_id"], row["broker"], e)
            await async_safe_update("broker_credentials", {"token_status": "needs_attention"}, "user_id", row["user_id"])
            results.append({
                "user_id": row["user_id"],
                "broker": row["broker"],
                "success": False,
                "error": f"credential decryption failed: {e}",
            })
            continue

        creds = {
            "client_id": client_id,
            "secret_key": secret_key,
            "access_token": existing_token,
            **row.get("additional_params", {}),
        }
        result = await refresh_user_token(row["user_id"], row["broker"], creds)
        results.append(result)

    success_count = sum(1 for r in results if r["success"])
    logger.info(
        "Token refresh complete: %d/%d succeeded",
        success_count, len(results),
    )
    return results


def effective_token_status(row: dict) -> tuple[str, bool]:
    """Derive a credential's status from the expiry beside it. Returns `(status, expired)`.

    `token_status` is written as `"valid"` when a credential is saved and is never written
    again, so on its own it describes the past. Measured in production on 2026-10-18:

        token_status     = "valid"
        token_expires_at = 2026-09-23T00:30:00+00:00     (25 days earlier)

    and the Fyers circuit breaker sat open with 137 consecutive failures while the user was
    told their broker was connected. Nothing read the column wrongly -- the column was simply
    never reconciled with the expiry in the same row.

    Deliberately kept inside the existing vocabulary (`valid` / `needs_attention` / `revoked` /
    `unknown`) so no consumer has to learn a new word; the precise fact travels alongside as the
    `expired` boolean instead.

    Two things this refuses to do. It does not upgrade a flagged credential because its expiry is
    in the future -- `needs_attention` can also mean "never completed" -- and it does not treat a
    missing expiry as an expired token, since several brokers store none at all.
    """
    stored = (row.get("token_status") or "").strip() or "unknown"
    raw_expiry = row.get("token_expires_at")

    expires_at: datetime | None = None
    if raw_expiry:
        if isinstance(raw_expiry, datetime):
            expires_at = raw_expiry
        else:
            try:
                expires_at = datetime.fromisoformat(str(raw_expiry))
            except ValueError:
                # An unparseable expiry is not evidence of death. Leaving it alone reports the
                # stored status, which is the honest answer when the date cannot be read.
                expires_at = None

    if expires_at is not None:
        if expires_at.tzinfo is None:
            # `fromisoformat` returns a naive datetime for a string with no offset, and
            # comparing that to an aware `now()` raises. A status read that raises 500s the page
            # that asks for it, so naive values are pinned to UTC rather than rejected.
            expires_at = expires_at.replace(tzinfo=UTC)
        expired = expires_at <= datetime.now(UTC)
    else:
        expired = False

    if stored in ("revoked", "unknown"):
        return stored, expired
    if expired:
        return "needs_attention", True
    return stored, expired


async def get_token_status(user_id: str, broker: str) -> dict:
    """Return the current token validity status for a user's broker.

    The status is derived from `token_expires_at`, not echoed from `token_status` -- see
    `effective_token_status` for why, and for the production measurement behind it.
    """
    supabase = get_supabase()
    row = await async_safe_execute(
        supabase.table("broker_credentials")
        .select("token_status, token_expires_at, last_token_refresh_at, broker")
        .eq("user_id", user_id)
        .eq("broker", broker)
        .limit(1)
    )
    if not row:
        return {"status": "unknown", "broker": broker, "expired": False}
    r = row[0]
    status, expired = effective_token_status(r)
    return {
        "status": status,
        "broker": r.get("broker", broker),
        "expires_at": r.get("token_expires_at"),
        "last_refresh_at": r.get("last_token_refresh_at"),
        "expired": expired,
    }


def main():
    """Entry point for standalone cron execution."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = asyncio.run(refresh_all_tokens())
    failed = [r for r in results if not r["success"]]
    if failed:
        logger.warning("%d token(s) failed to refresh", len(failed))
        for f in failed:
            logger.warning("  user=%s broker=%s error=%s", f["user_id"], f["broker"], f.get("error"))


if __name__ == "__main__":
    main()
