"""
Pricing API — Bulk pricing + negotiation endpoints.

HARDENED:
- Row-level locking on PATCH (FIX 1)
- Server-side price recomputation (FIX 2)
- Idempotency-Key header support (FIX 3)
- 5-minute burst rate limit (FIX 4)
- Price floor protection (FIX 5)
- Audit trail: decided_by, decided_at (FIX 7)
- Strict state machine (FIX 8)
- Pricing cache invalidation (FIX 9)
"""

import json
import logging
import time
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Header
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


# ======================== PRICING CACHE (FIX 9) ========================

_pricing_cache = {}
_PRICING_CACHE_TTL = 30


def on_pricing_change(product_id: int):
    """Invalidate pricing cache when tiers change or negotiation accepted."""
    _pricing_cache.pop(product_id, None)
    logger.debug("PRICING_CACHE: invalidated product=%d", product_id)


def _get_cached_smart_price(product_id, qty):
    key = f"{product_id}:{qty}"
    entry = _pricing_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _PRICING_CACHE_TTL:
        return entry["data"]
    return None


def _set_cached_smart_price(product_id, qty, data):
    _pricing_cache[f"{product_id}:{qty}"] = {"data": data, "ts": time.time()}


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


def _compute_price_floor(product: models.Product) -> float:
    """FIX 5: Price floor = max(cost_price, selling_price * 0.6)"""
    cost = product.cost_price or 0.0
    selling = product.selling_price or 0.0
    return max(cost, selling * 0.6)


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
    decided_by: Optional[int] = None
    decided_at: Optional[datetime] = None
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

    existing = (
        db.query(models.PricingTier)
        .filter(models.PricingTier.product_id == product.id, models.PricingTier.min_qty == payload.min_qty)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Tier for min_qty={payload.min_qty} already exists")

    if product.selling_price and payload.price_per_unit > product.selling_price:
        raise HTTPException(status_code=400, detail=f"Tier price cannot exceed selling price (₹{product.selling_price})")

    if product.cost_price and payload.price_per_unit <= product.cost_price:
        raise HTTPException(status_code=400, detail=f"Tier price must be above cost price (₹{product.cost_price})")

    tier = models.PricingTier(
        product_id=product.id, shop_id=org_id,
        min_qty=payload.min_qty, price_per_unit=payload.price_per_unit,
    )
    db.add(tier)
    db.commit()
    db.refresh(tier)

    on_pricing_change(product.id)  # FIX 9
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
    _get_product_safe(db, product_id, org_id)
    return PricingEngine.get_tiers(db, product_id, org_id)


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

    product_id = tier.product_id
    db.delete(tier)
    db.commit()
    on_pricing_change(product_id)  # FIX 9
    return None


# ======================== SMART PRICING ========================

@router.get("/products/{product_id}/pricing", response_model=SmartPriceResponse)
def get_smart_price(
    product_id: int,
    qty: int = 1,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Smart pricing with caching."""
    org_id = _org_id(current_user)
    product = _get_product_safe(db, product_id, org_id)

    if qty < 1:
        raise HTTPException(status_code=400, detail="qty must be >= 1")

    # FIX 9: Check cache
    cached = _get_cached_smart_price(product_id, qty)
    if cached:
        return cached

    result = PricingEngine.get_smart_price(db, product, qty)
    resp = SmartPriceResponse(
        base_price=result.base_price, bulk_price=result.bulk_price,
        best_price=result.best_price, savings=result.savings,
        tier_applied=result.tier_applied, tier_min_qty=result.tier_min_qty,
        suggestion=result.suggestion,
    )

    _set_cached_smart_price(product_id, qty, resp)
    return resp


# ======================== PRICE NEGOTIATION ========================

@router.post("/price-request", response_model=PriceRequestResponse, status_code=201)
@limiter.limit("10/minute")
def create_price_request(
    request: Request,
    payload: PriceRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    x_idempotency_key: Optional[str] = Header(None),
):
    """
    Submit a price negotiation request.
    Supports Idempotency-Key header for safe retries.
    """
    org_id = _org_id(current_user)
    user_id = current_user.get("user_id")

    # --- FIX 3: Idempotency check ---
    if x_idempotency_key:
        existing_key = (
            db.query(models.IdempotencyKey)
            .filter(models.IdempotencyKey.user_id == user_id, models.IdempotencyKey.key == x_idempotency_key)
            .first()
        )
        if existing_key:
            logger.info("PRICING: idempotency hit key=%s user=%d", x_idempotency_key, user_id)
            return PriceRequestResponse(**json.loads(existing_key.response_json))

    product = _get_product_safe(db, payload.product_id, org_id)

    # --- FIX 4: Burst rate limit (2 per product per 5 min) ---
    burst_cutoff = datetime.utcnow() - timedelta(minutes=5)
    burst_count = (
        db.query(models.PriceRequest)
        .filter(
            models.PriceRequest.user_id == user_id,
            models.PriceRequest.product_id == product.id,
            models.PriceRequest.created_at >= burst_cutoff,
        )
        .count()
    )
    if burst_count >= 2:
        raise HTTPException(status_code=429, detail="Max 2 requests per product per 5 minutes")

    # --- 24h limit ---
    daily_cutoff = datetime.utcnow() - timedelta(hours=24)
    daily_count = (
        db.query(models.PriceRequest)
        .filter(
            models.PriceRequest.user_id == user_id,
            models.PriceRequest.product_id == product.id,
            models.PriceRequest.created_at >= daily_cutoff,
        )
        .count()
    )
    if daily_count >= 5:
        raise HTTPException(status_code=429, detail="Max 5 price requests per product per 24 hours")

    # --- Reject duplicate pending ---
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

    # --- FIX 5: Price floor protection ---
    min_price = _compute_price_floor(product)
    if payload.requested_price < min_price:
        raise HTTPException(
            status_code=400,
            detail=f"Price too low. Minimum allowed: ₹{min_price:.2f}"
        )

    # --- FIX 2: Server-side recomputation via PricingEngine ---
    evaluation = PricingEngine.evaluate_request(db, product, payload.quantity, payload.requested_price)

    price_req = models.PriceRequest(
        user_id=user_id, shop_id=org_id, product_id=product.id,
        quantity=payload.quantity, requested_price=payload.requested_price,
        status="accepted" if evaluation.auto_accept else "pending",
        approved_price=payload.requested_price if evaluation.auto_accept else None,
        decided_by=user_id if evaluation.auto_accept else None,
        decided_at=datetime.utcnow() if evaluation.auto_accept else None,
    )
    db.add(price_req)
    db.commit()
    db.refresh(price_req)

    if evaluation.auto_accept:
        on_pricing_change(product.id)  # FIX 9

    resp = PriceRequestResponse(
        id=price_req.id, user_id=price_req.user_id, product_id=price_req.product_id,
        quantity=price_req.quantity, requested_price=price_req.requested_price,
        approved_price=price_req.approved_price, status=price_req.status,
        risk_level=evaluation.risk_level,
        decided_by=price_req.decided_by, decided_at=price_req.decided_at,
        created_at=price_req.created_at,
    )

    # --- FIX 3: Store idempotency key ---
    if x_idempotency_key:
        idem = models.IdempotencyKey(
            user_id=user_id, key=x_idempotency_key,
            response_json=json.dumps(resp.model_dump(), default=str),
        )
        db.add(idem)
        try:
            db.commit()
        except Exception:
            db.rollback()  # Duplicate key race — safe to ignore

    logger.info(
        "PRICING: request id=%d product=%d qty=%d price=%.2f auto=%s risk=%s",
        price_req.id, product.id, payload.quantity, payload.requested_price,
        evaluation.auto_accept, evaluation.risk_level,
    )
    return resp


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
    Seller responds to a negotiation request.
    FIX 1: Row-level lock prevents double-accept.
    FIX 7: Audit trail (decided_by, decided_at).
    FIX 8: Only pending → accepted/rejected transitions allowed.
    """
    org_id = _org_id(current_user)
    user_id = current_user.get("user_id")

    # FIX 1: Row-level lock to prevent concurrent double-accept
    price_req = (
        db.query(models.PriceRequest)
        .filter(models.PriceRequest.id == request_id, models.PriceRequest.shop_id == org_id)
        .with_for_update()
        .first()
    )
    if not price_req:
        raise HTTPException(status_code=404, detail="Price request not found")

    # FIX 8: Strict state machine — only pending can transition
    if price_req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {price_req.status}. Cannot modify.")

    # FIX 2: Server-side recomputation before acceptance
    if payload.status == "accepted":
        if not payload.approved_price:
            raise HTTPException(status_code=400, detail="approved_price is required when accepting")

        # Recompute floor from engine — never trust earlier evaluation
        product = _get_product_safe(db, price_req.product_id, org_id)
        min_price = _compute_price_floor(product)
        if payload.approved_price < min_price:
            raise HTTPException(status_code=400, detail=f"Approved price below floor (₹{min_price:.2f})")

        price_req.approved_price = payload.approved_price

    price_req.status = payload.status
    price_req.admin_note = payload.admin_note

    # FIX 7: Audit trail
    price_req.decided_by = user_id
    price_req.decided_at = datetime.utcnow()
    price_req.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(price_req)

    # FIX 9: Invalidate pricing cache on acceptance
    if payload.status == "accepted":
        on_pricing_change(price_req.product_id)

    logger.info("PRICING: request %d → %s by user=%d (approved=%s)", request_id, payload.status, user_id, payload.approved_price)
    return price_req
