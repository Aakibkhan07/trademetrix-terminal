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

from brokers import get_broker
from core.db import get_supabase
from core.safe_query import safe_execute, safe_update
from core.security import decrypt_broker_credentials, encrypt_broker_credentials

logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)


async def refresh_user_token(user_id: str, broker: str, creds: dict) -> dict:
    """Attempt to refresh a single user's broker token. Returns status dict."""
    try:
        adapter_cls = get_broker(broker)
        adapter = adapter_cls()
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

        safe_update("broker_credentials", update_data, "user_id", user_id)
        logger.info("Token refreshed: user=%s broker=%s", user_id, broker)
        return result

    except Exception as e:
        logger.warning("Token refresh failed: user=%s broker=%s error=%s", user_id, broker, e)
        safe_update("broker_credentials", {"token_status": "needs_attention"}, "user_id", user_id)
        return {
            "user_id": user_id,
            "broker": broker,
            "success": False,
            "error": str(e),
        }


async def refresh_all_tokens() -> list[dict]:
    """Iterate all active broker credentials and refresh tokens."""
    supabase = get_supabase()
    rows = safe_execute(
        supabase.table("broker_credentials")
        .select("*")
        .eq("is_active", True)
    )
    if not rows:
        logger.info("No active broker credentials to refresh")
        return []

    results = []
    for row in rows:
        creds = {
            "client_id": decrypt_broker_credentials(row["encrypted_api_key"]),
            "secret_key": decrypt_broker_credentials(row["encrypted_secret_key"]),
            "access_token": decrypt_broker_credentials(row.get("encrypted_access_token", "") or ""),
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


async def get_token_status(user_id: str, broker: str) -> dict:
    """Return the current token validity status for a user's broker."""
    supabase = get_supabase()
    row = safe_execute(
        supabase.table("broker_credentials")
        .select("token_status, token_expires_at, last_token_refresh_at, broker")
        .eq("user_id", user_id)
        .eq("broker", broker)
        .limit(1)
    )
    if not row:
        return {"status": "unknown", "broker": broker}
    r = row[0]
    return {
        "status": r.get("token_status", "unknown"),
        "broker": r.get("broker", broker),
        "expires_at": r.get("token_expires_at"),
        "last_refresh_at": r.get("last_token_refresh_at"),
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
