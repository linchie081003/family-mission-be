"""Platform activation email: resend verification, manual verify, welcome on activate."""

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import _register_payload


async def _register_unactivated(client: AsyncClient) -> dict:
    uid = uuid.uuid4().hex[:8]
    payload = _register_payload(uid)
    with patch.dict(os.environ, {"TESTING": "0"}):
        res = await client.post("/api/auth/register", json=payload)
    assert res.status_code == 200, res.text
    return {"family_id": res.json()["family_id"], "email": payload["email"]}


@pytest.mark.asyncio
async def test_platform_activation_email_flows(client: AsyncClient, platform_admin_headers: dict):
    reg = await _register_unactivated(client)

    with patch(
        "app.services.platform_service.send_verification_for_parent",
        new_callable=AsyncMock,
    ) as mock_send:
        resend = await client.post(
            f"/api/platform/families/{reg['family_id']}/resend-verification",
            headers=platform_admin_headers,
        )
        assert resend.status_code == 200, resend.text
        mock_send.assert_called_once()
        assert resend.json()["email_verified"] is False

    verify = await client.post(
        f"/api/platform/families/{reg['family_id']}/verify-email",
        headers=platform_admin_headers,
    )
    assert verify.status_code == 200, verify.text
    assert verify.json()["email_verified"] is True

    resend_blocked = await client.post(
        f"/api/platform/families/{reg['family_id']}/resend-verification",
        headers=platform_admin_headers,
    )
    assert resend_blocked.status_code == 400
    assert "sudah diverifikasi" in resend_blocked.json()["detail"].lower()

    reg2 = await _register_unactivated(client)
    with patch(
        "app.services.platform_service.send_tenant_activation_email",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_welcome:
        activate = await client.post(
            f"/api/platform/families/{reg2['family_id']}/activate",
            headers=platform_admin_headers,
            json={"preset": "standard"},
        )
        assert activate.status_code == 200, activate.text
        mock_welcome.assert_called_once()
        body = mock_welcome.call_args.kwargs
        assert body["family_name"]
        assert body["preset_label"] == "Standar"
        assert activate.json()["activated_at"] is not None
        assert activate.json()["activation_preset"] == "standard"
