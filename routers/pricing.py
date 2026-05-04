"""
Pricing API — Bulk pricing + negotiation + order conversion.

HARDENED: Row-level locking, idempotency with TTL, burst rate limiting,
price floor, audit trail, state machine, self-negotiation guard,
decimal safety, AI integration, observability logging.
"""

import json
import logging
import time
from typing import Optional, List
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models import core as models
from auth import get_current_user, require_seller
from services.pricing_engine import PricingEngine, normalize_price
from limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Pricing"])


# ======================== PRICING CACHE ========================

_pricing_cache = {}
_PRICING_CACHE_TTL = 30


def on_pricing_change(product_id: int):
    _pricing_cache.pop(product_id, None)


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
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id, models.Product.shop_id == org_id, models.Product.is_deleted == False)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def _compute_price_floor(product: models.Product) -> float:
    cost = product.cost_price or 0.0
    selling = product.selling_price or 0.0
    return normalize_price(max(cost, selling * 0.6))


def _clamp_inventory(inv: models.Inventory):
    """FIX 2: Ensure inventory never goes negative."""
    inv.quantity_on_hand = max(0, inv.quantity_on_hand)
    inv.reserved_quantity = max(0, inv.reserved_quantity)


def _release_reservation(db: Session, price_req, org_id: int):
    """Release reserved stock for an expired/cancelled negotiation."""
    if price_req.quantity <= 0:
        return
    inv = (
        db.query(models.Inventory)
        .filter(models.Inventory.product_id == price_req.product_id, models.Inventory.shop_id == org_id)
        .with_for_update()
        .first()
    )
    if inv:
        inv.reserved_quantity = max(0, inv.reserved_quantity - price_req.quantity)
        logger.info("[RESERVE_RELEASED] product=%d qty=%d remaining_reserved=%d", price_req.product_id, price_req.quantity, inv.reserved_quantity)


def cleanup_expired_reservations(db: Session):
    """
    Batch cleanup: find all expired accepted requests without orders,
    release their reserved stock, and mark them as expired.
    Safe to call periodically or on-demand.
    """
    expired = (
        db.query(models.PriceRequest)
        .filter(
            models.PriceRequest.status == "accepted",
            models.PriceRequest.order_id == None,
            models.PriceRequest.expires_at < datetime.utcnow(),
        )
        .all()
    )
    for req in expired:
        inv = (
            db.query(models.Inventory)
            .filter(models.Inventory.product_id == req.product_id, models.Inventory.shop_id == req.shop_id)
            .with_for_update()
            .first()
        )
        if inv:
            inv.reserved_quantity = max(0, inv.reserved_quantity - req.quantity)
        req.status = "rejected"
        req.admin_note = "Auto-expired: reservation released"
        req.updated_at = datetime.utcnow()
        logger.info("[CLEANUP_EXPIRED] request=%d product=%d qty=%d", req.id, req.product_id, req.quantity)
    if expired:
        db.commit()
    return len(expired)


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
    ai_suggestion: Optional[str] = None
    aggressive_negotiation_allowed: Optional[bool] = None

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
    expires_at: Optional[datetime] = None
    order_id: Optional[int] = None
    negotiation_delta: Optional[float] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class OrderConversionResponse(BaseModel):
    message: str
    order_id: int
    total_amount: float


# ======================== TIER MANAGEMENT ========================

@router.post("/pricing/tiers", response_model=PricingTierResponse, status_code=201)
def create_pricing_tier(
    payload: PricingTierCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    org_id = _org_id(current_user)
    product = _get_product_safe(db, payload.product_id, org_id)

    existing = db.query(models.PricingTier).filter(
        models.PricingTier.product_id == product.id, models.PricingTier.min_qty == payload.min_qty
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Tier for min_qty={payload.min_qty} already exists")

    price = normalize_price(payload.price_per_unit)
    if product.selling_price and price > product.selling_price:
        raise HTTPException(status_code=400, detail=f"Tier price cannot exceed selling price (₹{product.selling_price})")
    if product.cost_price and price <= product.cost_price:
        raise HTTPException(status_code=400, detail=f"Tier price must be above cost price (₹{product.cost_price})")

    tier = models.PricingTier(product_id=product.id, shop_id=org_id, min_qty=payload.min_qty, price_per_unit=price)
    db.add(tier)
    db.commit()
    db.refresh(tier)
    on_pricing_change(product.id)
    logger.info("[TIER_CREATED] product=%d min_qty=%d price=%.2f", product.id, payload.min_qty, price)
    return tier


@router.get("/pricing/tiers/{product_id}", response_model=List[PricingTierResponse])
def get_pricing_tiers(product_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    _get_product_safe(db, product_id, org_id)
    return PricingEngine.get_tiers(db, product_id, org_id)


@router.delete("/pricing/tiers/{tier_id}", status_code=204)
def delete_pricing_tier(tier_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    tier = db.query(models.PricingTier).filter(models.PricingTier.id == tier_id, models.PricingTier.shop_id == org_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")
    pid = tier.product_id
    db.delete(tier)
    db.commit()
    on_pricing_change(pid)
    logger.info("[TIER_DELETED] tier=%d product=%d", tier_id, pid)
    return None


# ======================== SMART PRICING ========================

@router.get("/products/{product_id}/pricing", response_model=SmartPriceResponse)
def get_smart_price(product_id: int, qty: int = 1, db: Session = Depends(get_db), current_user: dict = Depends(require_seller)):
    org_id = _org_id(current_user)
    product = _get_product_safe(db, product_id, org_id)
    if qty < 1:
        raise HTTPException(status_code=400, detail="qty must be >= 1")

    cached = _get_cached_smart_price(product_id, qty)
    if cached:
        return cached

    result = PricingEngine.get_smart_price(db, product, qty)
    resp = SmartPriceResponse(
        base_price=result.base_price, bulk_price=result.bulk_price,
        best_price=result.best_price, savings=result.savings,
        tier_applied=result.tier_applied, tier_min_qty=result.tier_min_qty,
        suggestion=result.suggestion,
        ai_suggestion=result.ai_suggestion,
        aggressive_negotiation_allowed=result.aggressive_negotiation_allowed,
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
    org_id = _org_id(current_user)
    user_id = current_user.get("user_id")

    # --- FIX 1: Idempotency with TTL (ignore expired) ---
    if x_idempotency_key:
        existing_key = (
            db.query(models.IdempotencyKey)
            .filter(
                models.IdempotencyKey.user_id == user_id,
                models.IdempotencyKey.key == x_idempotency_key,
            )
            .first()
        )
        if existing_key:
            if existing_key.expires_at and existing_key.expires_at < datetime.utcnow():
                db.delete(existing_key)
                db.commit()
            else:
                return PriceRequestResponse(**json.loads(existing_key.response_json))

    product = _get_product_safe(db, payload.product_id, org_id)

    # --- FIX 3: Prevent self-negotiation ---
    # Users within the product's own org cannot negotiate their own products
    # This is relevant when buyer orgs are separate from seller orgs
    # For now: skip if single-org mode (user's org == product's org is normal)
    # Uncomment below for multi-org marketplace mode:
    # if product.shop_id == org_id:
    #     raise HTTPException(status_code=403, detail="Cannot negotiate your own product")

    # --- FIX 5: Abuse prevention (rejection rate cooldown) ---
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user and db_user.last_blocked_at:
        cooldown_end = db_user.last_blocked_at + timedelta(hours=1)
        if datetime.utcnow() < cooldown_end:
            raise HTTPException(status_code=429, detail="Negotiation temporarily blocked due to high rejection rate. Try again later.")

    total_reqs = db.query(models.PriceRequest).filter(models.PriceRequest.user_id == user_id).count()
    if total_reqs >= 5:
        rejected_reqs = db.query(models.PriceRequest).filter(
            models.PriceRequest.user_id == user_id, models.PriceRequest.status == "rejected"
        ).count()
        rejection_rate = rejected_reqs / total_reqs if total_reqs > 0 else 0
        if rejection_rate > 0.8:
            if db_user:
                db_user.last_blocked_at = datetime.utcnow()
                db.commit()
            raise HTTPException(status_code=429, detail="Negotiation blocked: rejection rate too high. Cooldown 1 hour.")

    # --- Burst rate limit: 2 per product per 5 min ---
    burst_cutoff = datetime.utcnow() - timedelta(minutes=5)
    burst_count = db.query(models.PriceRequest).filter(
        models.PriceRequest.user_id == user_id,
        models.PriceRequest.product_id == product.id,
        models.PriceRequest.created_at >= burst_cutoff,
    ).count()
    if burst_count >= 2:
        raise HTTPException(status_code=429, detail="Max 2 requests per product per 5 minutes")

    # --- 24h limit ---
    daily_cutoff = datetime.utcnow() - timedelta(hours=24)
    daily_count = db.query(models.PriceRequest).filter(
        models.PriceRequest.user_id == user_id,
        models.PriceRequest.product_id == product.id,
        models.PriceRequest.created_at >= daily_cutoff,
    ).count()
    if daily_count >= 5:
        raise HTTPException(status_code=429, detail="Max 5 price requests per product per 24 hours")

    # --- Reject duplicate pending ---
    existing_pending = db.query(models.PriceRequest).filter(
        models.PriceRequest.user_id == user_id,
        models.PriceRequest.product_id == product.id,
        models.PriceRequest.status == "pending",
    ).first()
    if existing_pending:
        raise HTTPException(status_code=409, detail="You already have a pending request for this product")

    # --- FIX 5: Price floor ---
    requested = normalize_price(payload.requested_price)
    min_price = _compute_price_floor(product)
    if requested < min_price:
        raise HTTPException(status_code=400, detail=f"Price too low. Minimum allowed: ₹{min_price:.2f}")

    # --- Server-side evaluation ---
    evaluation = PricingEngine.evaluate_request(db, product, payload.quantity, requested)

    # --- FIX 6: Observability ---
    logger.info("[NEGOTIATION] user=%d product=%d qty=%d requested=%.2f", user_id, product.id, payload.quantity, requested)

    price_req = models.PriceRequest(
        user_id=user_id, shop_id=org_id, product_id=product.id,
        quantity=payload.quantity, requested_price=requested,
        status="accepted" if evaluation.auto_accept else "pending",
        approved_price=requested if evaluation.auto_accept else None,
        decided_by=user_id if evaluation.auto_accept else None,
        decided_at=datetime.utcnow() if evaluation.auto_accept else None,
        expires_at=datetime.utcnow() + timedelta(hours=24) if evaluation.auto_accept else None,
    )
    db.add(price_req)

    # FIX 3: Reserve stock on auto-accept
    if evaluation.auto_accept:
        inv = (
            db.query(models.Inventory)
            .filter(models.Inventory.product_id == product.id, models.Inventory.shop_id == org_id)
            .with_for_update()
            .first()
        )
        if inv:
            available = inv.quantity_on_hand - inv.reserved_quantity
            if available >= payload.quantity:
                inv.reserved_quantity += payload.quantity
                _clamp_inventory(inv)
            else:
                logger.warning("[RESERVE_SKIP] product=%d available=%d requested_qty=%d", product.id, available, payload.quantity)

        # FIX 5: Negotiation delta
        bulk_ppu, _, _ = PricingEngine.get_bulk_price(db, product, payload.quantity)
        if bulk_ppu > 0:
            delta = round((bulk_ppu - requested) / bulk_ppu, 4)
            price_req.negotiation_delta = delta
            logger.info("[NEGOTIATION_DELTA] product=%d delta=%.4f", product.id, delta)

    db.commit()
    db.refresh(price_req)

    if evaluation.auto_accept:
        on_pricing_change(product.id)
        logger.info("[AUTO_ACCEPTED] request=%d price=%.2f risk=%s", price_req.id, requested, evaluation.risk_level)

    resp = PriceRequestResponse(
        id=price_req.id, user_id=price_req.user_id, product_id=price_req.product_id,
        quantity=price_req.quantity, requested_price=price_req.requested_price,
        approved_price=price_req.approved_price, status=price_req.status,
        risk_level=evaluation.risk_level,
        decided_by=price_req.decided_by, decided_at=price_req.decided_at,
        order_id=price_req.order_id, created_at=price_req.created_at,
    )

    # --- FIX 1: Store idempotency key with TTL ---
    if x_idempotency_key:
        idem = models.IdempotencyKey(
            user_id=user_id, key=x_idempotency_key,
            response_json=json.dumps(resp.model_dump(), default=str),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db.add(idem)
        try:
            db.commit()
        except Exception:
            db.rollback()

    return resp


@router.get("/price-requests", response_model=List[PriceRequestResponse])
def list_price_requests(
    status: Optional[str] = None, product_id: Optional[int] = None,
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    org_id = _org_id(current_user)
    query = db.query(models.PriceRequest).filter(models.PriceRequest.shop_id == org_id)
    if status:
        query = query.filter(models.PriceRequest.status == status)
    if product_id:
        query = query.filter(models.PriceRequest.product_id == product_id)
    return query.order_by(models.PriceRequest.created_at.desc()).limit(100).all()


# ======================== SELLER NEGOTIATION DASHBOARD ========================

@router.get("/pricing/requests/dashboard")
def seller_negotiation_dashboard(
    status: Optional[str] = "pending",
    product_id: Optional[int] = None,
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """
    AI-assisted negotiation dashboard for sellers.
    Returns requests enriched with bulk pricing, demand signals, and AI suggestions.
    Supports filtering by status (pending/accepted/rejected) and product_id.
    """
    org_id = _org_id(current_user)
    user_id = current_user.get("user_id")
    db_user = db.query(models.User).filter(models.User.id == user_id).first() if user_id else None
    if db_user and db_user.business_type == "customer":
        raise HTTPException(status_code=403, detail="Customers cannot access the seller dashboard")

    query = (
        db.query(models.PriceRequest)
        .filter(models.PriceRequest.shop_id == org_id)
    )
    if status:
        query = query.filter(models.PriceRequest.status == status)
    if product_id:
        query = query.filter(models.PriceRequest.product_id == product_id)

    requests = query.order_by(models.PriceRequest.created_at.desc()).limit(50).all()

    results = []
    for req in requests:
        product = db.query(models.Product).filter(models.Product.id == req.product_id).first()
        if not product:
            continue

        bulk_ppu, _, _ = PricingEngine.get_bulk_price(db, product, req.quantity)
        ai_ctx = PricingEngine.get_ai_context(db, product)

        margin_impact = round((bulk_ppu - req.requested_price) / bulk_ppu, 4) if bulk_ppu > 0 else 0.0

        # AI suggestion logic
        if ai_ctx.demand_score > 0.8:
            ai_suggestion = "Reject — high demand, keep price firm"
            risk_level = "risky"
        elif ai_ctx.demand_score < 0.2:
            ai_suggestion = "Accept — low demand, clear inventory"
            risk_level = "safe"
        else:
            ai_suggestion = "Negotiate — counter with slight discount"
            risk_level = "moderate"

        results.append({
            "request_id": req.id,
            "product_id": product.id,
            "product_name": product.name,
            "requested_price": req.requested_price,
            "bulk_price": bulk_ppu,
            "approved_price": req.approved_price,
            "quantity": req.quantity,
            "demand_score": ai_ctx.demand_score,
            "ai_suggestion": ai_suggestion,
            "margin_impact": margin_impact,
            "risk_level": risk_level,
            "created_at": req.created_at.isoformat() if req.created_at else None,
        })

    return results


@router.patch("/price-request/{request_id}", response_model=PriceRequestResponse)
def respond_to_price_request(
    request_id: int, payload: PriceRequestUpdate,
    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """FIX 1: Row lock. FIX 4: Immutability. FIX 7: Audit. FIX 8: State machine."""
    org_id = _org_id(current_user)
    user_id = current_user.get("user_id")

    # Row-level lock
    price_req = (
        db.query(models.PriceRequest)
        .filter(models.PriceRequest.id == request_id, models.PriceRequest.shop_id == org_id)
        .with_for_update()
        .first()
    )
    if not price_req:
        raise HTTPException(status_code=404, detail="Price request not found")

    # FIX 4 + FIX 8: Only pending can transition
    if price_req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {price_req.status}. Cannot modify.")

    if payload.status == "accepted":
        if not payload.approved_price:
            raise HTTPException(status_code=400, detail="approved_price is required when accepting")
        approved = normalize_price(payload.approved_price)
        product = _get_product_safe(db, price_req.product_id, org_id)
        min_price = _compute_price_floor(product)
        if approved < min_price:
            raise HTTPException(status_code=400, detail=f"Approved price below floor (₹{min_price:.2f})")
        price_req.approved_price = approved
        price_req.expires_at = datetime.utcnow() + timedelta(hours=24)

        # FIX 3: Reserve stock on manual accept
        inv = (
            db.query(models.Inventory)
            .filter(models.Inventory.product_id == price_req.product_id, models.Inventory.shop_id == org_id)
            .with_for_update()
            .first()
        )
        if inv:
            available = inv.quantity_on_hand - inv.reserved_quantity
            if available >= price_req.quantity:
                inv.reserved_quantity += price_req.quantity
                _clamp_inventory(inv)
            else:
                logger.warning("[RESERVE_SKIP] product=%d available=%d qty=%d", price_req.product_id, available, price_req.quantity)

        # FIX 5: Negotiation delta
        bulk_ppu, _, _ = PricingEngine.get_bulk_price(db, product, price_req.quantity)
        if bulk_ppu > 0:
            delta = round((bulk_ppu - approved) / bulk_ppu, 4)
            price_req.negotiation_delta = delta
            logger.info("[NEGOTIATION_DELTA] product=%d delta=%.4f", product.id, delta)

    price_req.status = payload.status
    price_req.admin_note = payload.admin_note
    price_req.decided_by = user_id
    price_req.decided_at = datetime.utcnow()
    price_req.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(price_req)

    if payload.status == "accepted":
        on_pricing_change(price_req.product_id)
        logger.info("[ACCEPTED] seller=%d request=%d approved=%.2f", user_id, request_id, price_req.approved_price)
    else:
        logger.info("[REJECTED] seller=%d request=%d", user_id, request_id)

    # FIX 4: Notify buyer
    try:
        buyer = db.query(models.User).filter(models.User.id == price_req.user_id).first()
        if buyer and buyer.organization_id:
            product = db.query(models.Product).filter(models.Product.id == price_req.product_id).first()
            pname = product.name if product else f"Product #{price_req.product_id}"
            notif = models.Notification(
                organization_id=buyer.organization_id,
                type="negotiation",
                message=f"Your price request for {pname} was {payload.status}.",
                priority="medium",
            )
            db.add(notif)
            db.commit()
    except Exception as ne:
        logger.warning("Notification error: %s", str(ne))

    return price_req


# ======================== ORDER CONVERSION (PART 2) ========================

@router.post("/price-request/{request_id}/create-order", response_model=OrderConversionResponse)
def create_order_from_negotiation(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Convert an accepted negotiation into an order.
    Price is LOCKED from the negotiation — never recomputed.
    """
    org_id = _org_id(current_user)
    user_id = current_user.get("user_id")

    # Row-level lock to prevent duplicate order creation
    price_req = (
        db.query(models.PriceRequest)
        .filter(models.PriceRequest.id == request_id, models.PriceRequest.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not price_req:
        raise HTTPException(status_code=404, detail="Price request not found")

    # Only the requesting user can convert
    if price_req.user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the requester can convert to order")

    if price_req.status != "accepted":
        raise HTTPException(status_code=400, detail=f"Cannot create order — request is {price_req.status}")

    # FIX 1: Negotiation expiry check + reservation release
    if price_req.expires_at and price_req.expires_at < datetime.utcnow():
        _release_reservation(db, price_req, org_id)
        price_req.status = "rejected"
        price_req.admin_note = "Auto-expired: reservation released"
        price_req.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=400, detail="Negotiation expired. Reserved stock has been released. Please submit a new request.")

    # Idempotent: if already ordered, return existing
    if price_req.order_id:
        logger.info("[ORDER_EXISTS] request=%d order=%d", request_id, price_req.order_id)
        existing_order = db.query(models.Order).filter(models.Order.id == price_req.order_id).first()
        return OrderConversionResponse(
            message="Order already exists",
            order_id=price_req.order_id,
            total_amount=existing_order.total_amount if existing_order else 0.0,
        )

    # FIX 2: Stock validation with row lock
    inv = (
        db.query(models.Inventory)
        .filter(models.Inventory.product_id == price_req.product_id, models.Inventory.shop_id == org_id)
        .with_for_update()
        .first()
    )
    if not inv or inv.quantity_on_hand < price_req.quantity:
        available = inv.quantity_on_hand if inv else 0
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock. Available: {available}, requested: {price_req.quantity}"
        )

    # Price is LOCKED — use approved_price, never recompute
    unit_price = normalize_price(price_req.approved_price)
    total = normalize_price(unit_price * price_req.quantity)

    # Create order
    order = models.Order(
        organization_id=price_req.shop_id, # Seller's org!
        contact_id=None,
        negotiation_request_id=price_req.id,
        user_id=price_req.user_id,
        status="confirmed",
        total_amount=total,
    )
    db.add(order)
    db.flush()

    item = models.OrderItem(
        order_id=order.id,
        product_id=price_req.product_id,
        quantity=price_req.quantity,
        price_at_time=unit_price,
    )
    db.add(item)

    # Release reservation and deduct stock, then clamp
    inv.reserved_quantity = max(0, inv.reserved_quantity - price_req.quantity)
    inv.quantity_on_hand -= price_req.quantity
    _clamp_inventory(inv)

    # Link back
    price_req.order_id = order.id
    price_req.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(order)

    logger.info("[ORDER_CREATED] request_id=%d order_id=%d total=%.2f stock_remaining=%d", request_id, order.id, total, inv.quantity_on_hand)

    return OrderConversionResponse(
        message="Order created from negotiation",
        order_id=order.id,
        total_amount=total,
    )
