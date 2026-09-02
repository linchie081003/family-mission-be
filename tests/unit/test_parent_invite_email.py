from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_invite_reports_email_not_sent_when_unconfigured(
    client: AsyncClient,
    registered_parent: dict,
):
    headers = registered_parent["headers"]
    with patch("app.services.parent_service.send_coparent_invite_email", AsyncMock(return_value=False)):
        res = await client.post(
            "/api/parents/invite",
            headers=headers,
            json={"email": "coparent-new@example.com", "name": "Co Parent", "role": "mother"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email_sent"] is False
    assert "belum terkirim" in body["message"]
