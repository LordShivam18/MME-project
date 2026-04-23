"""
End-to-end integration flow test.

Validates the full user journey in one test:
  Login → Create Product → Add Stock → Record Sale → Fetch Prediction

Each step asserts correctness before proceeding. Uses UUID-based
identifiers for complete isolation from other test data.
"""

import pytest
from tests.conftest import uid


async def test_full_inventory_flow(client):
    """Complete user flow: login → product → stock → sale → prediction."""

    # ── Step 1: Login ─────────────────────────────────────────
    login_resp = await client.post(
        "/api/v1/login",
        data={"username": "test@gmail.com", "password": "123456"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    tokens = login_resp.json()
    assert "access_token" in tokens
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # ── Step 2: Create Product ────────────────────────────────
    sku = f"FLOW-{uid()}"
    product_resp = await client.post("/api/v1/products/", json={
        "name": f"FlowTest {sku}",
        "sku": sku,
        "category": "Integration",
        "cost_price": 15.00,
        "selling_price": 40.00,
        "lead_time_days": 5,
    }, headers=headers)
    assert product_resp.status_code == 200, f"Create product failed: {product_resp.text}"
    product = product_resp.json()
    pid = product["id"]
    assert product["sku"] == sku
    assert product["selling_price"] == 40.00

    # ── Step 3: Add Stock ─────────────────────────────────────
    stock_resp = await client.post("/api/v1/inventory/add-stock", json={
        "product_id": pid,
        "quantity": 100,
    }, headers=headers)
    assert stock_resp.status_code == 200, f"Add stock failed: {stock_resp.text}"
    assert stock_resp.json()["quantity_on_hand"] == 100

    # ── Step 4: Record Sale (verify atomic deduction) ─────────
    sale_resp = await client.post("/api/v1/sales/", json={
        "product_id": pid,
        "quantity_sold": 10,
    }, headers=headers)
    assert sale_resp.status_code == 200, f"Record sale failed: {sale_resp.text}"
    assert sale_resp.json()["stock_left"] == 90

    # Verify inventory reflects the deduction
    inv_resp = await client.get(f"/api/v1/inventory/{pid}", headers=headers)
    assert inv_resp.status_code == 200
    assert inv_resp.json()["quantity_on_hand"] == 90

    # ── Step 5: Fetch Prediction ──────────────────────────────
    pred_resp = await client.get(f"/api/v1/predictions/{pid}", headers=headers)
    assert pred_resp.status_code == 200, f"Prediction failed: {pred_resp.text}"
    prediction = pred_resp.json()
    # Validate prediction structure
    assert "product_id" in prediction
    assert "insight" in prediction
    assert "recommended_action" in prediction
    assert "confidence_score" in prediction
    assert "predicted_daily_demand" in prediction
    assert prediction["product_id"] == pid

    # ── Cleanup: soft-delete product ──────────────────────────
    del_resp = await client.delete(f"/api/v1/products/{pid}", headers=headers)
    assert del_resp.status_code == 200
