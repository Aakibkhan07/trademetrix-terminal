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


async def send_telegram_alert(message: str, parse_mode: str = "HTML") -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("[DEV] No Telegram configured — would send: %s", message[:80])
        return False
    try:
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Telegram alert sent")
                return True
            logger.warning("Telegram send failed: %s", resp.text)
            return False
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
        return False


RESEND_FROM = "TradeMetrix <onboarding@resend.dev>"


async def send_email_resend(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> bool:
    if not settings.resend_api_key:
        logger.info("[DEV] No Resend API key — would send email to %s: %s", to_email, subject)
        return False
    try:
        payload: dict = {
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": subject,
            "text": text_body,
        }
        if html_body:
            payload["html"] = html_body
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("Resend email failed: status=%s body=%s", resp.status_code, resp.text[:500])
                return False
            return True
    except Exception as e:
        logger.warning("Resend email exception: %s", e)
        return False


async def send_otp_email_resend(email: str, otp: str) -> bool:
    return await send_email_resend(
        email,
        "Your TradeMetrix OTP",
        f"Your TradeMetrix OTP is {otp}. Valid for 5 minutes.",
    )


async def send_welcome_email(to_email: str, user_name: str) -> bool:
    subject = "Welcome to TradeMetrix!"
    text_body = (
        f"Hi {user_name},\n\n"
        f"Welcome to TradeMetrix! Your account has been created successfully.\n\n"
        f"Start exploring the platform and set up your trading strategies.\n\n"
        f"Best,\nThe TradeMetrix Team"
    )
    html_body = (
        f"<h2>Welcome to TradeMetrix!</h2>"
        f"<p>Hi {user_name},</p>"
        f"<p>Your account has been created successfully.</p>"
        f"<p>Start exploring the platform and set up your trading strategies.</p>"
        f"<br><p>Best,<br>The TradeMetrix Team</p>"
    )
    return await send_email_resend(to_email, subject, text_body, html_body)


async def send_admin_notification_email(
    to_email: str,
    role: str,
    assigned_by: str | None = None,
) -> bool:
    subject = "You have been granted admin access on TradeMetrix"
    text_body = (
        f"Hi,\n\n"
        f"You have been granted the '{role}' admin role on TradeMetrix."
        + (f" This was assigned by {assigned_by}." if assigned_by else "")
        + "\n\n"
        f"You now have access to the admin panel and administrative features.\n\n"
        f"Best,\nThe TradeMetrix Team"
    )
    html_body = (
        f"<h2>Admin Access Granted</h2>"
        f"<p>You have been granted the <strong>{role}</strong> admin role on TradeMetrix."
        + (f" This was assigned by {assigned_by}." if assigned_by else "")
        + "</p>"
        f"<p>You now have access to the admin panel and administrative features.</p>"
        f"<br><p>Best,<br>The TradeMetrix Team</p>"
    )
    return await send_email_resend(to_email, subject, text_body, html_body)


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
        sent = await send_otp_email_resend(email, otp)
    if not sent:
        logger.info("[DEV] OTP %s for %s (no delivery service configured)", otp, email)
    return sent
