import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html: str) -> bool:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        logger.warning("SMTP not configured — cannot send email")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _smtp_send, msg)
        logger.info("Email sent to %s", to)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


def _smtp_send(msg: MIMEMultipart) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from, msg["To"], msg.as_string())
