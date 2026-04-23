"""
Product CRUD endpoint tests.

Covers: create, duplicate SKU rejection, list, update, soft-delete.
All operations go through real /api/v1/* routes with JWT auth.
Uses UUID-based SKUs — zero collision risk across parallel runs.
"""

import pytest
from tests.conftest import uid


def _product_payload(sku=None):
    sku = sku or f"TEST-{uid()}"
    return {
        "name": f"TestProduct {sku}",
        "sku": sku,
        "category": "Testing",
        "cost_price": 10.50,
        "selling_price": 25.00,
        "lead_time_days": 5,
    }


async def test_create_product(client, auth_headers):
    """Create product via API (org-scoped, plan-limited)."""
    payload = _product_payload()
    resp = await client.post("/api/v1/products/", json=payload, headers=auth_headers)
    assert resp.status_code == 200, f"Create failed: {resp.text}"
    body = resp.json()
    assert "id" in body
    assert body["sku"] == payload["sku"]

    # Cleanup: soft-delete
    await client.delete(f"/api/v1/products/{body['id']}", headers=auth_headers)


async def test_duplicate_sku_rejected(client, auth_headers):
    """Same SKU within an org must be rejected."""
    sku = f"DUP-{uid()}"
    payload = _product_payload(sku)

    # First create succeeds
    r1 = await client.post("/api/v1/products/", json=payload, headers=auth_headers)
    assert r1.status_code == 200
    pid = r1.json()["id"]

    # Duplicate fails
    r2 = await client.post("/api/v1/products/", json=payload, headers=auth_headers)
    assert r2.status_code == 400
    assert "SKU already exists" in r2.json()["detail"]

    # Cleanup
    await client.delete(f"/api/v1/products/{pid}", headers=auth_headers)


async def test_list_products(client, auth_headers):
    """List products returns 200 and a list."""
    resp = await client.get("/api/v1/products/", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_update_product(client, auth_headers):
    """Update product fields via PUT."""
    sku = f"UPD-{uid()}"
    payload = _product_payload(sku)
    create = await client.post("/api/v1/products/", json=payload, headers=auth_headers)
    assert create.status_code == 200
    pid = create.json()["id"]

    updated = {**payload, "name": "UpdatedName", "selling_price": 50.00}
    resp = await client.put(f"/api/v1/products/{pid}", json=updated, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "UpdatedName"
    assert resp.json()["selling_price"] == 50.00

    # Cleanup
    await client.delete(f"/api/v1/products/{pid}", headers=auth_headers)


async def test_soft_delete_excludes_product(client, auth_headers):
    """Soft-deleted product should not appear in list."""
    sku = f"DEL-{uid()}"
    create = await client.post("/api/v1/products/", json=_product_payload(sku), headers=auth_headers)
    assert create.status_code == 200
    pid = create.json()["id"]

    # Delete
    resp = await client.delete(f"/api/v1/products/{pid}", headers=auth_headers)
    assert resp.status_code == 200

    # Verify excluded
    listing = await client.get("/api/v1/products/", headers=auth_headers)
    ids = [p["id"] for p in listing.json()]
    assert pid not in ids


async def test_products_require_auth(client):
    """Product endpoints reject unauthenticated requests."""
    resp = await client.get("/api/v1/products/")
    assert resp.status_code == 401
