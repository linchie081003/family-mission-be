import asyncio
import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _sender_email() -> str:
    return (
        settings.brevo_sender_email
        or settings.smtp_from
        or settings.smtp_user
        or settings.platform_admin_email
    )


def _sender_name() -> str:
    return settings.brevo_sender_name or "Family Mission"


def _send_brevo_sync(*, to: str, subject: str, body: str) -> bool:
    if not settings.brevo_api_key or not to:
        return False
    payload = {
        "sender": {"name": _sender_name(), "email": _sender_email()},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    req = urllib.request.Request(
        BREVO_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": settings.brevo_api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return 200 <= resp.status < 300


def _send_smtp_sync(*, to: str, subject: str, body: str) -> bool:
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


def email_provider_status() -> dict:
    sender = _sender_email()
    if settings.brevo_api_key:
        provider = "brevo"
    elif settings.smtp_host:
        provider = "smtp"
    else:
        provider = "none"
    return {
        "provider": provider,
        "brevo_key_set": bool(settings.brevo_api_key),
        "smtp_host_set": bool(settings.smtp_host),
        "sender_email_set": bool(sender),
    }


async def send_email(*, to: str, subject: str, body: str) -> bool:
    if not to:
        return False
    if settings.brevo_api_key:
        try:
            return await asyncio.to_thread(_send_brevo_sync, to=to, subject=subject, body=body)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode(errors="replace")[:500]
            logger.error("Brevo API HTTP %s for %s: %s", exc.code, to, err_body)
            if "unrecognised IP" in err_body or "authorised_ips" in err_body:
                logger.error(
                    "Brevo blocked server IP (common on Render). "
                    "Disable IP restriction or add IP at https://app.brevo.com/security/authorised_ips"
                )
            elif "sender" in err_body.lower() and "not valid" in err_body.lower():
                logger.error(
                    "Brevo rejected sender %s — verify this address or authenticate the domain at "
                    "https://app.brevo.com/senders",
                    _sender_email(),
                )
            return False
        except Exception:
            logger.exception("Failed to send email via Brevo to %s", to)
            return False
    if settings.smtp_host:
        try:
            return await asyncio.to_thread(_send_smtp_sync, to=to, subject=subject, body=body)
        except Exception:
            logger.exception("Failed to send email via SMTP to %s", to)
            return False
    logger.info("Email not configured — skip email to %s: %s", to, subject)
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
