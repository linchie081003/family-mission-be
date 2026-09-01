import io
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services import email_service


@pytest.mark.asyncio
async def test_send_email_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(email_service.settings, "brevo_api_key", "")
    monkeypatch.setattr(email_service.settings, "smtp_host", "")
    ok = await email_service.send_email(to="user@example.com", subject="Hi", body="Test")
    assert ok is False


@pytest.mark.asyncio
async def test_send_email_uses_brevo_when_api_key_set(monkeypatch):
    monkeypatch.setattr(email_service.settings, "brevo_api_key", "test-key")
    monkeypatch.setattr(email_service.settings, "brevo_sender_email", "noreply@example.com")
    monkeypatch.setattr(email_service.settings, "smtp_host", "")

    captured: dict = {}

    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        resp = MagicMock()
        resp.status = 201
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch("app.services.email_service.urllib.request.urlopen", fake_urlopen):
        ok = await email_service.send_email(
            to="parent@example.com",
            subject="Verifikasi Email — Family Mission",
            body="Klik link",
        )

    assert ok is True
    assert captured["url"] == email_service.BREVO_API_URL
    assert captured["headers"]["Api-key"] == "test-key"
    assert captured["body"]["to"] == [{"email": "parent@example.com"}]
    assert captured["body"]["sender"]["email"] == "noreply@example.com"
    assert captured["body"]["textContent"] == "Klik link"


@pytest.mark.asyncio
async def test_send_email_falls_back_to_smtp_without_brevo(monkeypatch):
    monkeypatch.setattr(email_service.settings, "brevo_api_key", "")
    monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "smtp_port", 587)
    monkeypatch.setattr(email_service.settings, "smtp_use_tls", False)
    monkeypatch.setattr(email_service.settings, "smtp_user", "")
    monkeypatch.setattr(email_service.settings, "smtp_from", "noreply@example.com")

    sent = {"called": False}

    class FakeSMTP:
        def __init__(self, host, port, timeout=15):
            assert host == "smtp.example.com"
            assert port == 587

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            raise AssertionError("starttls should not run when smtp_use_tls is false")

        def login(self, user, password):
            raise AssertionError("login should not run without smtp_user")

        def send_message(self, msg):
            sent["called"] = True
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]

    with patch("app.services.email_service.smtplib.SMTP", FakeSMTP):
        ok = await email_service.send_email(to="user@example.com", subject="Subj", body="Body")

    assert ok is True
    assert sent["called"] is True
    assert sent["to"] == "user@example.com"
    assert sent["subject"] == "Subj"


@pytest.mark.asyncio
async def test_send_verification_email_delegates_to_send_email(monkeypatch):
    monkeypatch.setattr(email_service.settings, "email_token_expire_hours", 24)
    calls: list[dict] = []

    async def fake_send_email(**kwargs):
        calls.append(kwargs)
        return True

    with patch.object(email_service, "send_email", fake_send_email):
        ok = await email_service.send_verification_email(
            to="new@example.com",
            link="http://localhost:5173/verify-email?token=abc",
        )

    assert ok is True
    assert len(calls) == 1
    assert calls[0]["to"] == "new@example.com"
    assert "Verifikasi Email" in calls[0]["subject"]
    assert "http://localhost:5173/verify-email?token=abc" in calls[0]["body"]
    assert "24 jam" in calls[0]["body"]


@pytest.mark.asyncio
async def test_brevo_http_error_returns_false(monkeypatch):
    monkeypatch.setattr(email_service.settings, "brevo_api_key", "bad-key")
    monkeypatch.setattr(email_service.settings, "smtp_host", "")

    import urllib.error

    def raise_http(*args, **kwargs):
        raise urllib.error.HTTPError(
            email_service.BREVO_API_URL,
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"invalid API key"}'),
        )

    with patch("app.services.email_service.urllib.request.urlopen", raise_http):
        ok = await email_service.send_email(to="user@example.com", subject="Hi", body="Test")

    assert ok is False
