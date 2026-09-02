import uuid

import pytest
from httpx import AsyncClient

TEST_PASSWORD = "Secret123!"


def _register_payload(uid: str) -> dict:
    return {
        "email": f"delete-tenant-{uid}@example.com",
        "password": TEST_PASSWORD,
        "confirm_password": TEST_PASSWORD,
        "family_name": f"Delete Test {uid}",
        "name": f"Orang Tua {uid}",
        "role": "father",
        "accept_terms": True,
        "accept_privacy": True,
        "accept_parental_consent": True,
        "accept_child_data_protection": True,
    }


@pytest.mark.asyncio
async def test_delete_inactive_tenant(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    reg = await client.post("/api/auth/register", json=_register_payload(uid))
    assert reg.status_code == 200, reg.text
    family_id = reg.json()["family_id"]

    deactivate = await client.patch(
        f"/api/platform/families/{family_id}/features",
        json={"is_active": False},
        headers=platform_admin_headers,
    )
    assert deactivate.status_code == 200, deactivate.text

    delete = await client.delete(
        f"/api/platform/families/{family_id}",
        headers=platform_admin_headers,
    )
    assert delete.status_code == 200, delete.text
    body = delete.json()
    assert "berhasil dihapus" in body["message"]
    assert body["deleted"]["id"] == family_id

    login = await client.post(
        "/api/auth/login",
        json={"email": f"delete-tenant-{uid}@example.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_delete_active_tenant_rejected(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    reg = await client.post("/api/auth/register", json=_register_payload(uid))
    assert reg.status_code == 200, reg.text
    family_id = reg.json()["family_id"]

    delete = await client.delete(
        f"/api/platform/families/{family_id}",
        headers=platform_admin_headers,
    )
    assert delete.status_code == 400, delete.text
    assert "Nonaktifkan" in delete.json()["detail"]
