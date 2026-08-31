"""Billing lifecycle integration tests."""

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_PASSWORD, _register_payload

PROOF_IMAGE = "data:image/png;base64,iVBORw0KGgo="


@pytest.mark.asyncio
async def test_billing_lifecycle_flow(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    payload = _register_payload(uid)
    reg = await client.post("/api/auth/register", json=payload)
    assert reg.status_code == 200, reg.text
    family_id = reg.json()["family_id"]

    manual = await client.post(
        f"/api/platform/families/{family_id}/verify-email",
        headers=platform_admin_headers,
    )
    assert manual.status_code == 200, manual.text

    login = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": TEST_PASSWORD},
    )
    assert login.status_code == 200, login.text
    parent_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    sub_res = await client.get("/api/billing/subscription", headers=parent_headers)
    assert sub_res.status_code == 200, sub_res.text
    sub = sub_res.json()
    assert sub["status"] == "trial"
    assert sub["plan_slug"] == "family"

    plans_res = await client.get("/api/platform/plans", headers=platform_admin_headers)
    assert plans_res.status_code == 200

    await client.patch(
        "/api/platform/billing/payment-settings",
        headers=platform_admin_headers,
        json={
            "bank_name": "BCA",
            "bank_account_number": "1234567890",
            "bank_account_holder": "Family Mission",
            "payment_methods_enabled": {"qris_static": False, "bank_transfer": True},
        },
    )

    upgrade = await client.post(
        "/api/billing/upgrade-request",
        headers=parent_headers,
        json={
            "plan_slug": "standard",
            "method": "bank_transfer",
            "provider_ref": "TRX123",
            "proof_image": PROOF_IMAGE,
        },
    )
    assert upgrade.status_code == 200, upgrade.text
    payment_id = upgrade.json()["payment_id"]

    pending = await client.get("/api/billing/pending-payment", headers=parent_headers)
    assert pending.status_code == 200
    assert pending.json()["payment_id"] == payment_id
    assert pending.json()["has_proof"] is True

    notifs = await client.get("/api/platform/notifications", headers=platform_admin_headers)
    assert notifs.status_code == 200
    assert any(n["type"] == "payment_proof_uploaded" for n in notifs.json())

    pay = await client.post(
        f"/api/platform/payments/{payment_id}/confirm",
        headers=platform_admin_headers,
    )
    assert pay.status_code == 200, pay.text
    assert pay.json()["subscription_id"] is not None

    sub_after = await client.get("/api/billing/subscription", headers=parent_headers)
    assert sub_after.status_code == 200
    assert sub_after.json()["plan_slug"] == "standard"
    assert sub_after.json()["status"] == "active"


@pytest.mark.asyncio
async def test_upgrade_requires_proof(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    payload = _register_payload(uid)
    reg = await client.post("/api/auth/register", json=payload)
    assert reg.status_code == 200
    family_id = reg.json()["family_id"]
    await client.post(
        f"/api/platform/families/{family_id}/verify-email",
        headers=platform_admin_headers,
    )
    login = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": TEST_PASSWORD},
    )
    parent_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    await client.patch(
        "/api/platform/billing/payment-settings",
        headers=platform_admin_headers,
        json={
            "bank_account_number": "999",
            "payment_methods_enabled": {"bank_transfer": True, "qris_static": False},
        },
    )

    bad = await client.post(
        "/api/billing/upgrade-request",
        headers=parent_headers,
        json={"plan_slug": "standard", "method": "bank_transfer"},
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_demo_plan_assign_and_revoke(client: AsyncClient, platform_admin_headers: dict):
    uid = uuid.uuid4().hex[:8]
    payload = _register_payload(uid)
    reg = await client.post("/api/auth/register", json=payload)
    assert reg.status_code == 200
    family_id = reg.json()["family_id"]
    await client.post(
        f"/api/platform/families/{family_id}/verify-email",
        headers=platform_admin_headers,
    )

    assign = await client.post(
        f"/api/platform/families/{family_id}/assign-plan",
        headers=platform_admin_headers,
        json={"plan_slug": "family", "is_demo": True, "note": "Partner demo"},
    )
    assert assign.status_code == 200, assign.text
    body = assign.json()
    assert body["is_demo"] is True
    assert body["plan_slug"] == "family"

    login = await client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": TEST_PASSWORD},
    )
    parent_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    sub = await client.get("/api/billing/subscription", headers=parent_headers)
    assert sub.status_code == 200
    assert sub.json()["is_demo"] is True
    assert sub.json()["plan_slug"] == "family"

    revoke = await client.post(
        f"/api/platform/families/{family_id}/revoke-demo",
        headers=platform_admin_headers,
    )
    assert revoke.status_code == 200
    assert revoke.json()["is_demo"] is False

    sub_after = await client.get("/api/billing/subscription", headers=parent_headers)
    assert sub_after.json()["plan_slug"] == "basic"
    assert sub_after.json()["is_demo"] is False
