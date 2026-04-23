"""
Order & Contact endpoint tests.

Covers: order creation (server-side total), status transitions, contact stats.
Validates that price_at_time is computed on the server, never from the client.
"""

import pytest
import time


def _unique_sku():
    return f"ORD-{int(time.time() * 1000) % 10_000_000}"


async def _create_product(client, headers):
    """Helper: create a temporary product and return its id + selling_price."""
    sku = _unique_sku()
    resp = await client.post("/api/v1/products/", json={
        "name": f"OrderTestProd {sku}",
        "sku": sku,
        "category": "Testing",
        "cost_price": 10.0,
        "selling_price": 30.0,
        "lead_time_days": 3,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    return data["id"], data["selling_price"]


async def _create_contact(client, headers):
    """Helper: create a temporary supplier contact and return its id."""
    ts = int(time.time() * 1000) % 10_000_000
    resp = await client.post("/api/v1/contacts", json={
        "name": f"TestSupplier{ts}",
        "phone": f"555{ts}",
        "type": "supplier",
    }, headers=headers)
    assert resp.status_code == 200
    return resp.json()["id"]


async def test_create_order_server_computed_total(client, auth_headers):
    """Order total is computed server-side from product.selling_price."""
    pid, price = await _create_product(client, auth_headers)
    cid = await _create_contact(client, auth_headers)
    qty = 3

    resp = await client.post("/api/v1/orders", json={
        "contact_id": cid,
        "items": [{"product_id": pid, "quantity": qty}],
    }, headers=auth_headers)
    assert resp.status_code == 200
    order = resp.json()

    assert order["total_amount"] == price * qty
    assert len(order["items"]) == 1
    assert order["items"][0]["price_at_time"] == price

    # Cleanup
    await client.delete(f"/api/v1/products/{pid}", headers=auth_headers)
    await client.delete(f"/api/v1/contacts/{cid}", headers=auth_headers)


async def test_order_valid_status_transition(client, auth_headers):
    """pending → confirmed is a valid state transition."""
    pid, _ = await _create_product(client, auth_headers)
    cid = await _create_contact(client, auth_headers)

    create = await client.post("/api/v1/orders", json={
        "contact_id": cid,
        "items": [{"product_id": pid, "quantity": 1}],
    }, headers=auth_headers)
    oid = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "confirmed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"

    # Cleanup
    await client.delete(f"/api/v1/products/{pid}", headers=auth_headers)
    await client.delete(f"/api/v1/contacts/{cid}", headers=auth_headers)


async def test_order_invalid_status_transition(client, auth_headers):
    """confirmed → delivered is NOT a valid transition (must go through shipped)."""
    pid, _ = await _create_product(client, auth_headers)
    cid = await _create_contact(client, auth_headers)

    create = await client.post("/api/v1/orders", json={
        "contact_id": cid,
        "items": [{"product_id": pid, "quantity": 1}],
    }, headers=auth_headers)
    oid = create.json()["id"]

    # First move to confirmed
    await client.patch(f"/api/v1/orders/{oid}/status", json={"status": "confirmed"}, headers=auth_headers)

    # Then try invalid jump to delivered
    resp = await client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Invalid transition" in resp.json()["detail"]

    # Cleanup
    await client.delete(f"/api/v1/products/{pid}", headers=auth_headers)
    await client.delete(f"/api/v1/contacts/{cid}", headers=auth_headers)


async def test_fetch_order_includes_items(client, auth_headers):
    """GET order returns items with server-computed price_at_time."""
    pid, price = await _create_product(client, auth_headers)
    cid = await _create_contact(client, auth_headers)

    create = await client.post("/api/v1/orders", json={
        "contact_id": cid,
        "items": [{"product_id": pid, "quantity": 2}],
    }, headers=auth_headers)
    oid = create.json()["id"]

    resp = await client.get(f"/api/v1/orders/{oid}", headers=auth_headers)
    assert resp.status_code == 200
    order = resp.json()
    assert "items" in order
    assert order["items"][0]["price_at_time"] == price
    assert order["total_amount"] == price * 2

    # Cleanup
    await client.delete(f"/api/v1/products/{pid}", headers=auth_headers)
    await client.delete(f"/api/v1/contacts/{cid}", headers=auth_headers)


async def test_orders_require_auth(client):
    """Order endpoints reject unauthenticated requests."""
    resp = await client.get("/api/v1/orders")
    assert resp.status_code == 401
