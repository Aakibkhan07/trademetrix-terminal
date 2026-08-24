"""Telegram alert link management (per-user)."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from core.config import settings
from core.deps import get_current_user
from core.models import UserProfile
from core.telegram import telegram_gateway

router = APIRouter(prefix="/notifications/telegram", tags=["notifications"])
logger = logging.getLogger(__name__)


def _mask(chat_id: str) -> str:
    if len(chat_id) <= 4:
        return "***"
    return f"{chat_id[:2]}***{chat_id[-3:]}"


@router.get("/status")
async def status(current_user: UserProfile = Depends(get_current_user)):
    link = await telegram_gateway.get_link(current_user.id)
    return {
        "configured": telegram_gateway.configured,
        "linked": bool(link),
        "chat_id_masked": _mask(link["chat_id"]) if link else None,
        "username": (link or {}).get("username") or None,
        "linked_at": (link or {}).get("linked_at"),
    }


@router.post("/link")
async def create_link(current_user: UserProfile = Depends(get_current_user)):
    if not telegram_gateway.configured:
        raise HTTPException(status_code=503, detail="Telegram alerts are not configured yet — check back soon")
    bot_username = await telegram_gateway.get_bot_username()
    code = await telegram_gateway.create_link_code(current_user.id)
    if not code or not bot_username:
        raise HTTPException(status_code=503, detail="Telegram bot unavailable — try again shortly")
    url = f"https://t.me/{bot_username}?start={code}"
    logger.info("Telegram link code issued for user %s", current_user.id)
    return {"url": url, "expires_in_seconds": 600}


@router.delete("/link")
async def unlink(current_user: UserProfile = Depends(get_current_user)):
    ok = await telegram_gateway.unlink(current_user.id)
    return {"unlinked": ok}
