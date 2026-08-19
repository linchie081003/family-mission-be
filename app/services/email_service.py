import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_sync(*, to: str, subject: str, body: str) -> bool:
    if not settings.smtp_host or not to:
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user or settings.platform_admin_email
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
    return True


async def send_email(*, to: str, subject: str, body: str) -> bool:
    if not settings.smtp_host:
        logger.info("SMTP not configured — skip email to %s: %s", to, subject)
        return False
    try:
        return await asyncio.to_thread(_send_sync, to=to, subject=subject, body=body)
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
