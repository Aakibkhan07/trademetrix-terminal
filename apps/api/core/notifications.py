import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


async def send_otp_sms(phone: str, otp: str) -> bool:
    if not settings.fast2sms_api_key:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://www.fast2sms.com/dev/bulkV2",
                headers={"authorization": settings.fast2sms_api_key},
                json={
                    "sender_id": "TXTIND",
                    "message": f"Your TradeMetrix OTP is {otp}. Valid for 5 minutes.",
                    "language": "english",
                    "route": "q",
                    "numbers": phone,
                },
                timeout=10,
            )
            return resp.status_code == 200
    except Exception as e:
        logger.warning("Fast2SMS failed: %s", e)
        return False


async def send_otp_whatsapp(phone: str, otp: str) -> bool:
    if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_whatsapp_from]):
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={
                    "From": f"whatsapp:{settings.twilio_whatsapp_from}",
                    "Body": f"Your TradeMetrix OTP is {otp}. Valid for 5 minutes.",
                    "To": f"whatsapp:+91{phone}",
                },
                timeout=10,
            )
            return resp.status_code == 201
    except Exception as e:
        logger.warning("Twilio WhatsApp failed: %s", e)
        return False


async def send_otp_email(email: str, otp: str) -> bool:
    if not settings.smtp_host:
        return False
    try:
        msg = MIMEText(f"Your TradeMetrix OTP is {otp}. Valid for 5 minutes.")
        msg["Subject"] = "Your TradeMetrix OTP"
        msg["From"] = settings.smtp_from
        msg["To"] = email
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_user:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.warning("Email send failed: %s", e)
        return False


async def send_alert_email(email: str, subject: str, body: str) -> bool:
    if not settings.smtp_host:
        logger.info("[DEV] No SMTP configured — would email %s: %s", email, subject)
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = email
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_user:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("Alert email sent to %s: %s", email, subject)
        return True
    except Exception as e:
        logger.warning("Alert email failed: %s", e)
        return False


async def send_alert_sms(phone: str, body: str) -> bool:
    if not settings.fast2sms_api_key:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://www.fast2sms.com/dev/bulkV2",
                headers={"authorization": settings.fast2sms_api_key},
                json={"sender_id": "TXTIND", "message": body, "language": "english", "route": "q", "numbers": phone},
                timeout=10,
            )
            return resp.status_code == 200
    except Exception as e:
        logger.warning("Alert SMS failed: %s", e)
        return False


async def send_alert_whatsapp(phone: str, body: str) -> bool:
    if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_whatsapp_from]):
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={"From": f"whatsapp:{settings.twilio_whatsapp_from}", "Body": body, "To": f"whatsapp:+91{phone}"},
                timeout=10,
            )
            return resp.status_code == 201
    except Exception as e:
        logger.warning("Alert WhatsApp failed: %s", e)
        return False


async def deliver_otp(otp: str, email: str, phone: str = "") -> bool:
    logger.info("[OTP] Code for %s: %s", email, otp)

    sent = False
    if phone:
        sent = await send_otp_sms(phone, otp)
        if not sent:
            sent = await send_otp_whatsapp(phone, otp)
    if not sent:
        sent = await send_otp_email(email, otp)
    if not sent:
        logger.info("[DEV] OTP %s for %s (no delivery service configured)", otp, email)
    return sent
