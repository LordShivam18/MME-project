"""
Billing endpoint tests.

Covers: billing status, upgrade, downgrade, double-downgrade edge case.
Uses simulated billing flow (Stripe not configured in test environment).
"""

import pytest

pytestmark = [pytest.mark.billing]


async def test_billing_status(client, auth_headers):
    """GET billing status returns plan, limits, and usage."""
    resp = await client.get("/api/v1/billing/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "plan" in data
    assert "limits" in data
    assert "usage" in data
    assert "products" in data["usage"]
    assert "users" in data["usage"]


@pytest.mark.flaky(reruns=2, reruns_delay=1)
async def test_upgrade_to_pro(client, auth_headers):
    """Upgrade to pro plan succeeds (simulated when Stripe not configured)."""
    resp = await client.post(
        "/api/v1/billing/upgrade",
        json={"plan": "pro"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Verify plan changed
    status = await client.get("/api/v1/billing/status", headers=auth_headers)
    assert status.json()["plan"] == "pro"


@pytest.mark.flaky(reruns=2, reruns_delay=1)
async def test_downgrade_to_free(client, auth_headers):
    """Downgrade from pro to free succeeds."""
    # Ensure we're on pro first
    await client.post(
        "/api/v1/billing/upgrade",
        json={"plan": "pro"},
        headers=auth_headers,
    )

    resp = await client.post("/api/v1/billing/downgrade", headers=auth_headers)
    assert resp.status_code == 200
    assert "free" in resp.json().get("message", "").lower() or resp.json().get("plan") == "free"

    # Verify plan
    status = await client.get("/api/v1/billing/status", headers=auth_headers)
    assert status.json()["plan"] == "free"


async def test_double_downgrade_rejected(client, auth_headers):
    """Downgrade when already on free returns 400."""
    # Ensure free plan
    await client.post(
        "/api/v1/billing/upgrade",
        json={"plan": "pro"},
        headers=auth_headers,
    )
    await client.post("/api/v1/billing/downgrade", headers=auth_headers)

    # Second downgrade should fail
    resp = await client.post("/api/v1/billing/downgrade", headers=auth_headers)
    assert resp.status_code == 400
    assert "Already on the free plan" in resp.json()["detail"]


async def test_billing_requires_auth(client):
    """Billing endpoints reject unauthenticated requests."""
    resp = await client.get("/api/v1/billing/status")
    assert resp.status_code == 401
