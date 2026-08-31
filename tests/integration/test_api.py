import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_PASSWORD, _register_payload


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    res = await client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["architecture"] == "mvc"


@pytest.mark.asyncio
async def test_parent_register_and_login(client: AsyncClient):
    uid = uuid.uuid4().hex[:8]
    payload = _register_payload(uid)
    register = await client.post("/api/auth/register", json=payload)
    assert register.status_code == 200
    reg_data = register.json()
    assert reg_data["status"] == "pending_verification"
    assert reg_data["family_id"]

    login = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "parent"

    bad_login = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": "WrongPass1!"},
    )
    assert bad_login.status_code == 401


@pytest.mark.asyncio
async def test_parent_me_requires_auth(client: AsyncClient):
    res = await client.get("/api/auth/me")
    assert res.status_code == 403 or res.status_code == 401


@pytest.mark.asyncio
async def test_parent_settings_flow(client: AsyncClient, registered_parent: dict):
    headers = registered_parent["headers"]

    me = await client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["family_name"].startswith("Keluarga Test")

    patch = await client.patch(
        "/api/settings",
        headers=headers,
        json={"rupiah_per_point": 2000, "daily_point_limit": 40, "note": "ci test"},
    )
    assert patch.status_code == 200
    assert patch.json()["rupiah_per_point"] == 2000

    audit = await client.get("/api/audit?limit=10", headers=headers)
    assert audit.status_code == 200
    logs = audit.json()
    assert any(log["entity_type"] == "settings" for log in logs)


@pytest.mark.asyncio
async def test_platform_admin_login(client: AsyncClient, platform_admin_headers: dict):
    del platform_admin_headers
    res = await client.post(
        "/api/platform/auth/login",
        json={"email": "admin@familymission.local", "password": "admin123456"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "platform_admin"
