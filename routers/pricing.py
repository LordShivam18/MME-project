"""
Pricing API — Bulk pricing + negotiation endpoints.

All endpoints are authenticated and multi-tenant safe.
All pricing logic goes through PricingEngine (service layer).
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models import core as models
from auth import get_current_user
from services.pricing_engine import PricingEngine
from limiter import limiter
from fastapi import Request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Pricing"])


# ======================== HELPERS ========================

def _org_id(current_user: dict) -> int:
    return current_user.get("organization_id") or current_user.get("user_id")


def _get_product_safe(db: Session, product_id: int, org_id: int) -> models.Product:
    """Fetch product with multi-tenant safety. Raises 404 if not found."""
    product = (
        db.query(models.Product)
        .filter(
            models.Product.id == product_id,
            models.Product.shop_id == org_id,
            models.Product.is_deleted == False,
        )
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ======================== SCHEMAS ========================

class PricingTierCreate(BaseModel):
    product_id: int
    min_qty: int = Field(..., gt=0, le=100000)
    price_per_unit: float = Field(..., gt=0, le=9999999.99)


class PricingTierResponse(BaseModel):
    id: int
    product_id: int
    min_qty: int
    price_per_unit: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SmartPriceResponse(BaseModel):
    base_price: float
    bulk_price: float
    best_price: float
    savings: float
    tier_applied: bool
    tier_min_qty: Optional[int] = None
    suggestion: Optional[str] = None


class PriceRequestCreate(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0, le=100000)
    requested_price: float = Field(..., gt=0, le=9999999.99)


class PriceRequestUpdate(BaseModel):
    status: str = Field(..., pattern="^(accepted|rejected)$")
    approved_price: Optional[float] = Field(None, gt=0, le=9999999.99)
    admin_note: Optional[str] = None


class PriceRequestResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    quantity: int
    requested_price: float
    approved_price: Optional[float] = None
    status: str
    admin_note: Optional[str] = None
    risk_level: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ======================== TIER MANAGEMENT ========================

@router.post("/pricing/tiers", response_model=PricingTierResponse, status_code=201)
def create_pricing_tier(
    payload: PricingTierCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a bulk pricing tier for a product. Admin only."""
    org_id = _org_id(current_user)
    product = _get_product_safe(db, payload.product_id, org_id)

    # Check for duplicate tier
    existing = (
        db.query(models.PricingTier)
        .filter(
            models.PricingTier.product_id == product.id,
            models.PricingTier.min_qty == payload.min_qty,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Tier for min_qty={payload.min_qty} already exists")

    # Validate: tier price should be <= selling price
    if product.selling_price and payload.price_per_unit > product.selling_price:
        raise HTTPException(
            status_code=400,
            detail=f"Tier price (₹{payload.price_per_unit}) cannot exceed selling price (₹{product.selling_price})"
        )

    # Validate: tier price should be > cost price
    if product.cost_price and payload.price_per_unit <= product.cost_price:
        raise HTTPException(
            status_code=400,
            detail=f"Tier price (₹{payload.price_per_unit}) must be above cost price (₹{product.cost_price})"
        )

    tier = models.PricingTier(
        product_id=product.id,
        shop_id=org_id,
        min_qty=payload.min_qty,
        price_per_unit=payload.price_per_unit,
    )
    db.add(tier)
    db.commit()
    db.refresh(tier)

    logger.info("PRICING: tier created product=%d min_qty=%d price=%.2f", product.id, payload.min_qty, payload.price_per_unit)
    return tier


@router.get("/pricing/tiers/{product_id}", response_model=List[PricingTierResponse])
def get_pricing_tiers(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List all pricing tiers for a product."""
    org_id = _org_id(current_user)
    _get_product_safe(db, product_id, org_id)  # Tenant check

    tiers = PricingEngine.get_tiers(db, product_id, org_id)
    return tiers


@router.delete("/pricing/tiers/{tier_id}", status_code=204)
def delete_pricing_tier(
    tier_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a pricing tier."""
    org_id = _org_id(current_user)
    tier = (
        db.query(models.PricingTier)
        .filter(models.PricingTier.id == tier_id, models.PricingTier.shop_id == org_id)
        .first()
    )
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")

    db.delete(tier)
    db.commit()
    return None


# ======================== SMART PRICING ========================

@router.get("/products/{product_id}/pricing", response_model=SmartPriceResponse)
def get_smart_price(
    product_id: int,
    qty: int = 1,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get smart pricing for a product at a given quantity.
    Returns base, bulk, best price, savings, and upsell suggestion.
    """
    org_id = _org_id(current_user)
    product = _get_product_safe(db, product_id, org_id)

    if qty < 1:
        raise HTTPException(status_code=400, detail="qty must be >= 1")

    result = PricingEngine.get_smart_price(db, product, qty)

    return SmartPriceResponse(
        base_price=result.base_price,
        bulk_price=result.bulk_price,
        best_price=result.best_price,
        savings=result.savings,
        tier_applied=result.tier_applied,
        tier_min_qty=result.tier_min_qty,
        suggestion=result.suggestion,
    )


# ======================== PRICE NEGOTIATION ========================

@router.post("/price-request", response_model=PriceRequestResponse, status_code=201)
@limiter.limit("10/minute")
def create_price_request(
    request: Request,
    payload: PriceRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit a price negotiation request.
    Rate limited: max 10/minute.
    Max 5 pending requests per product per user per 24h.
    """
    org_id = _org_id(current_user)
    user_id = current_user.get("user_id")
    product = _get_product_safe(db, payload.product_id, org_id)

    # --- Anti-spam: max 5 requests per product per user per 24h ---
    cutoff = datetime.utcnow() - timedelta(hours=24)
    recent_count = (
        db.query(models.PriceRequest)
        .filter(
            models.PriceRequest.user_id == user_id,
            models.PriceRequest.product_id == product.id,
            models.PriceRequest.created_at >= cutoff,
        )
        .count()
    )
    if recent_count >= 5:
        raise HTTPException(status_code=429, detail="Max 5 price requests per product per 24 hours")

    # --- Reject duplicate pending requests ---
    existing_pending = (
        db.query(models.PriceRequest)
        .filter(
            models.PriceRequest.user_id == user_id,
            models.PriceRequest.product_id == product.id,
            models.PriceRequest.status == "pending",
        )
        .first()
    )
    if existing_pending:
        raise HTTPException(status_code=409, detail="You already have a pending request for this product")

    # --- Reject under-cost pricing ---
    if product.cost_price and payload.requested_price <= product.cost_price:
        raise HTTPException(
            status_code=400,
            detail=f"Requested price cannot be at or below cost (₹{product.cost_price:.2f})"
        )

    # --- Evaluate via PricingEngine ---
    evaluation = PricingEngine.evaluate_request(db, product, payload.quantity, payload.requested_price)

    # --- Create request ---
    price_req = models.PriceRequest(
        user_id=user_id,
        shop_id=org_id,
        product_id=product.id,
        quantity=payload.quantity,
        requested_price=payload.requested_price,
        status="accepted" if evaluation.auto_accept else "pending",
        approved_price=payload.requested_price if evaluation.auto_accept else None,
    )
    db.add(price_req)
    db.commit()
    db.refresh(price_req)

    logger.info(
        "PRICING: request created id=%d product=%d qty=%d price=%.2f auto_accept=%s risk=%s",
        price_req.id, product.id, payload.quantity, payload.requested_price,
        evaluation.auto_accept, evaluation.risk_level,
    )

    return PriceRequestResponse(
        id=price_req.id,
        user_id=price_req.user_id,
        product_id=price_req.product_id,
        quantity=price_req.quantity,
        requested_price=price_req.requested_price,
        approved_price=price_req.approved_price,
        status=price_req.status,
        risk_level=evaluation.risk_level,
        created_at=price_req.created_at,
    )


@router.get("/price-requests", response_model=List[PriceRequestResponse])
def list_price_requests(
    status: Optional[str] = None,
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List all price requests for the current organization."""
    org_id = _org_id(current_user)
    query = db.query(models.PriceRequest).filter(models.PriceRequest.shop_id == org_id)

    if status:
        query = query.filter(models.PriceRequest.status == status)
    if product_id:
        query = query.filter(models.PriceRequest.product_id == product_id)

    return query.order_by(models.PriceRequest.created_at.desc()).limit(100).all()


@router.patch("/price-request/{request_id}", response_model=PriceRequestResponse)
def respond_to_price_request(
    request_id: int,
    payload: PriceRequestUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Seller responds to a price negotiation request.
    Only the product owner (same org) can approve/reject.
    """
    org_id = _org_id(current_user)

    price_req = (
        db.query(models.PriceRequest)
        .filter(
            models.PriceRequest.id == request_id,
            models.PriceRequest.shop_id == org_id,
        )
        .first()
    )
    if not price_req:
        raise HTTPException(status_code=404, detail="Price request not found")

    if price_req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {price_req.status}")

    # On accept: approved_price is required
    if payload.status == "accepted":
        if not payload.approved_price:
            raise HTTPException(status_code=400, detail="approved_price is required when accepting")
        price_req.approved_price = payload.approved_price

    price_req.status = payload.status
    price_req.admin_note = payload.admin_note
    price_req.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(price_req)

    logger.info("PRICING: request %d → %s (approved_price=%s)", request_id, payload.status, payload.approved_price)
    return price_req
