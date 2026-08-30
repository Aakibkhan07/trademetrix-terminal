from fastapi import APIRouter, Request, HTTPException
import os
from core.config import settings
from core.notifications import send_email_resend
from core.telegram import telegram_gateway

router = APIRouter(prefix="/reports", tags=["reports"])

@router.post("/daily/send")
async def send_daily_reports(request: Request):
    secret = request.headers.get("X-Cron-Secret") or request.query_params.get("secret")
    expected = os.getenv("CRON_SECRET") or settings.secret_key[:16]
    # In dev, allow without secret; in prod, require it if CRON_SECRET is set
    if os.getenv("CRON_SECRET") and secret != expected:
        raise HTTPException(status_code=401, detail="Invalid cron secret")

    # Scaffold: in production this would iterate over active users and push
    # via Resend + Telegram. We return the wiring status so the frontend
    # can show whether auto-send is configured.
    resend_ok = bool(settings.resend_api_key)
    telegram_ok = bool(settings.telegram_bot_token)
    return {
        "ok": True,
        "resend_configured": resend_ok,
        "telegram_configured": telegram_ok,
        "message": "Daily report scaffold — add cron 0 18 * * 1-5 curl -s http://127.0.0.1:8000/api/v1/reports/daily/send -H \"X-Cron-Secret: $CRON_SECRET\"",
        "hint": "Set RESEND_API_KEY and TELEGRAM_BOT_TOKEN in VPS .env to enable real pushes; journal data is at /ai/journal?lookback_days=1",
    }

@router.get("/daily")
async def get_daily_report():
    return {
        "date": __import__("datetime").datetime.now().isoformat()[:10],
        "note": "Use /ai/journal?lookback_days=1 for real daily P&L; this scaffold confirms wiring",
    }
