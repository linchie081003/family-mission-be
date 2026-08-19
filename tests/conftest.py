import os
import uuid

# Must be set before importing application modules.
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://family:family123@localhost:5432/family_mission",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-min-32-chars")
os.environ.setdefault("PLATFORM_ADMIN_EMAIL", "admin@familymission.local")
os.environ.setdefault("PLATFORM_ADMIN_PASSWORD", "admin123456")
os.environ.setdefault("RATE_LIMIT_AUTH_PER_MINUTE", "1000")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def registered_parent(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    email = f"parent-{uid}@example.com"
    password = "secret123"
    payload = {
        "email": email,
        "password": password,
        "family_name": f"Keluarga Test {uid}",
    }
    res = await client.post("/api/auth/register", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    approve = await client.patch(
        f"/api/platform/families/{data['family_id']}/features",
        headers=platform_admin_headers,
        json={"is_active": True},
    )
    assert approve.status_code == 200, approve.text
    login = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {
        "token": token,
        "family_id": data["family_id"],
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest_asyncio.fixture
async def platform_admin_headers(client: AsyncClient):
    res = await client.post(
        "/api/platform/auth/login",
        json={"email": "admin@familymission.local", "password": "admin123456"},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest_asyncio.fixture
async def quiz_parent(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    email = f"quiz-{uid}@example.com"
    password = "secret123"
    res = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "family_name": f"Quiz Keluarga {uid}",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    enable = await client.patch(
        f"/api/platform/families/{data['family_id']}/features",
        headers=platform_admin_headers,
        json={"quiz_enabled": True, "is_active": True},
    )
    assert enable.status_code == 200, enable.text
    login = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "family_id": data["family_id"],
    }
