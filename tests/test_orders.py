"""
Order & Contact endpoint tests.

Covers: order creation (server-side total), status transitions, contact stats.
Validates that price_at_time is computed on the server, never from the client.
Uses temp_product / temp_contact fixtures for automatic cleanup.
"""

import time
import pytest
from tests.conftest import assert_response_time, PERF_THRESHOLD_STANDARD, PERF_THRESHOLD_HEAVY

pytestmark = [pytest.mark.orders]


@pytest.mark.flaky(reruns=2, reruns_delay=1)
async def test_create_order_server_computed_total(client, auth_headers, temp_product, temp_contact):
    """Order total is computed server-side from product.selling_price."""
    pid, price = temp_product
    cid = temp_contact
    qty = 3

    t0 = time.time()
    resp = await client.post("/api/v1/orders", json={
        "contact_id": cid,
        "items": [{"product_id": pid, "quantity": qty}],
    }, headers=auth_headers)
    assert resp.status_code == 200
    order = resp.json()

    assert order["total_amount"] == price * qty
    assert len(order["items"]) == 1
    assert order["items"][0]["price_at_time"] == price
    assert_response_time(t0, PERF_THRESHOLD_HEAVY, "create order")


@pytest.mark.flaky(reruns=2, reruns_delay=1)
async def test_order_valid_status_transition(client, auth_headers, temp_product, temp_contact):
    """pending → confirmed is a valid state transition."""
    pid, _ = temp_product
    cid = temp_contact

    create = await client.post("/api/v1/orders", json={
        "contact_id": cid,
        "items": [{"product_id": pid, "quantity": 1}],
    }, headers=auth_headers)
    assert create.status_code == 200
    oid = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "confirmed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


async def test_order_invalid_status_transition(client, auth_headers, temp_product, temp_contact):
    """confirmed → delivered is NOT a valid transition (must go through shipped)."""
    pid, _ = temp_product
    cid = temp_contact

    create = await client.post("/api/v1/orders", json={
        "contact_id": cid,
        "items": [{"product_id": pid, "quantity": 1}],
    }, headers=auth_headers)
    assert create.status_code == 200
    oid = create.json()["id"]

    # First move to confirmed
    await client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "confirmed"},
        headers=auth_headers,
    )

    # Then try invalid jump to delivered
    resp = await client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Invalid transition" in resp.json()["detail"]


@pytest.mark.perf
@pytest.mark.flaky(reruns=2, reruns_delay=1)
async def test_fetch_order_includes_items(client, auth_headers, temp_product, temp_contact):
    """GET order returns items with server-computed price_at_time."""
    pid, price = temp_product
    cid = temp_contact

    create = await client.post("/api/v1/orders", json={
        "contact_id": cid,
        "items": [{"product_id": pid, "quantity": 2}],
    }, headers=auth_headers)
    assert create.status_code == 200
    oid = create.json()["id"]

    t0 = time.time()
    resp = await client.get(f"/api/v1/orders/{oid}", headers=auth_headers)
    assert resp.status_code == 200
    order = resp.json()
    assert "items" in order
    assert order["items"][0]["price_at_time"] == price
    assert order["total_amount"] == price * 2
    assert_response_time(t0, PERF_THRESHOLD_STANDARD, "fetch order")


async def test_orders_require_auth(client):
    """Order endpoints reject unauthenticated requests."""
    resp = await client.get("/api/v1/orders")
    assert resp.status_code == 401
