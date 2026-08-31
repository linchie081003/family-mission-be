import json
import os
import time
import uuid
from pathlib import Path

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
os.environ.setdefault("RATE_LIMIT_GLOBAL_PER_MINUTE", "10000")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app

TEST_PASSWORD = "Secret123!"
_DEBUG_LOG = Path(__file__).resolve().parents[3] / "debug-b984bf.log"


def _debug_log(hypothesis_id: str, message: str, data: dict) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "b984bf",
            "hypothesisId": hypothesis_id,
            "location": "conftest.py",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
            "runId": "lifespan-fix",
        }
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    # #endregion


def _register_payload(uid: str) -> dict:
    email = f"parent-{uid}@example.com"
    return {
        "email": email,
        "password": TEST_PASSWORD,
        "confirm_password": TEST_PASSWORD,
        "family_name": f"Keluarga Test {uid}",
        "name": f"Orang Tua {uid}",
        "role": "father",
        "accept_terms": True,
        "accept_privacy": True,
        "accept_parental_consent": True,
        "accept_child_data_protection": True,
    }


@pytest_asyncio.fixture(scope="session")
async def _app_lifespan():
    """Run FastAPI startup once per session (migrations, seed plans, platform admin)."""
    _debug_log("H1", "lifespan_enter", {"fixture": "_app_lifespan"})
    async with app.router.lifespan_context(app):
        _debug_log("H1", "lifespan_startup_complete", {"fixture": "_app_lifespan"})
        yield
    _debug_log("H1", "lifespan_shutdown", {"fixture": "_app_lifespan"})


@pytest_asyncio.fixture
async def client(_app_lifespan):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        _debug_log("H2", "client_ready", {"has_lifespan_parent": True})
        yield ac


@pytest_asyncio.fixture
async def registered_parent(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    payload = _register_payload(uid)
    res = await client.post("/api/auth/register", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    enable = await client.post(
        f"/api/platform/families/{data['family_id']}/activate",
        headers=platform_admin_headers,
        json={"preset": "family"},
    )
    assert enable.status_code == 200, enable.text
    login = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": TEST_PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {
        "token": token,
        "family_id": data["family_id"],
        "headers": {"Authorization": f"Bearer {token}"},
        "email": payload["email"],
    }


@pytest_asyncio.fixture
async def platform_admin_headers(client: AsyncClient):
    res = await client.post(
        "/api/platform/auth/login",
        json={"email": "admin@familymission.local", "password": "admin123456"},
    )
    _debug_log(
        "H3",
        "platform_admin_login",
        {"status_code": res.status_code, "ok": res.status_code == 200},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest_asyncio.fixture
async def quiz_parent(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    payload = _register_payload(uid)
    payload["email"] = f"quiz-{uid}@example.com"
    res = await client.post("/api/auth/register", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    enable = await client.patch(
        f"/api/platform/families/{data['family_id']}/features",
        headers=platform_admin_headers,
        json={"quiz_enabled": True},
    )
    assert enable.status_code == 200, enable.text
    login = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": TEST_PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "family_id": data["family_id"],
    }
