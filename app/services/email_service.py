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


async def send_verification_email(*, to: str, link: str) -> bool:
    body = f"""Halo,

Terima kasih telah mendaftar di Family Mission.

Klik link berikut untuk verifikasi email Anda (berlaku {settings.email_token_expire_hours} jam):
{link}

Jika Anda tidak mendaftar, abaikan email ini.

— Family Mission
"""
    return await send_email(to=to, subject="Verifikasi Email — Family Mission", body=body)


async def send_password_reset_email(*, to: str, link: str) -> bool:
    body = f"""Halo,

Kami menerima permintaan reset password untuk akun Family Mission Anda.

Klik link berikut untuk set password baru (berlaku {settings.reset_token_expire_minutes} menit):
{link}

Jika Anda tidak meminta reset, abaikan email ini.

— Family Mission
"""
    return await send_email(to=to, subject="Reset Password — Family Mission", body=body)


async def send_coparent_invite_email(*, to: str, inviter_name: str, family_name: str, link: str) -> bool:
    body = f"""Halo,

{inviter_name} mengundang Anda bergabung sebagai orang tua di keluarga "{family_name}" di Family Mission.

Klik link berikut untuk menerima undangan dan set password:
{link}

— Family Mission
"""
    return await send_email(to=to, subject=f"Undangan Co-Parent — {family_name}", body=body)


async def send_tenant_activation_email(
    *, to: str, family_name: str, preset_label: str, login_url: str
) -> bool:
    body = f"""Halo,

Akun keluarga "{family_name}" telah diaktifkan oleh Super Admin Family Mission dengan preset {preset_label}.

Anda dapat login dan mulai menggunakan aplikasi di:
{login_url}

— Family Mission
"""
    return await send_email(to=to, subject=f"Akun Diaktifkan — {family_name}", body=body)


async def send_referral_invite_email(*, to: str, referrer_name: str, link: str) -> bool:
    body = f"""Halo,

{referrer_name} mengundang keluarga Anda bergabung di Family Mission — aplikasi gamifikasi kebiasaan baik untuk keluarga.

Daftar melalui link berikut:
{link}

— Family Mission
"""
    return await send_email(to=to, subject="Undangan Family Mission", body=body)
