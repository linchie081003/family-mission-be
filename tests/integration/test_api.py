import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    res = await client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["architecture"] == "mvc"


TEST_REGISTER = {
    "email": "integration@example.com",
    "password": "Secret123!",
    "confirm_password": "Secret123!",
    "family_name": "Integration Test",
    "name": "Test Parent",
    "role": "father",
    "accept_terms": True,
    "accept_privacy": True,
    "accept_parental_consent": True,
    "accept_child_data_protection": True,
}


@pytest.mark.asyncio
async def test_parent_register_and_login(client: AsyncClient):
    register = await client.post("/api/auth/register", json=TEST_REGISTER)
    assert register.status_code == 200
    reg_data = register.json()
    assert reg_data["status"] == "pending_verification"
    assert reg_data["family_id"]

    login = await client.post(
        "/api/auth/login",
        json={"email": TEST_REGISTER["email"], "password": TEST_REGISTER["password"]},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "parent"

    bad_login = await client.post(
        "/api/auth/login",
        json={"email": TEST_REGISTER["email"], "password": "WrongPass1!"},
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
async def test_platform_admin_login(client: AsyncClient):
    res = await client.post(
        "/api/platform/auth/login",
        json={"email": "admin@familymission.local", "password": "admin123456"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "platform_admin"
