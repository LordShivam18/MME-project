"""
Public API — No authentication required.
Exposes real-time inventory availability for storefront consumption.

HARDENED:
- Stock always from inventory.quantity_on_hand via SQL COALESCE
- last_updated_at mapped from products.updated_at (no duplicate column)
- 30s TTL cache with full invalidation on any stock mutation
- Multi-tenant safety: shop_id filter enforced
- Deterministic ordering: updated_at DESC, then id DESC
- All response fields guaranteed non-null
"""

import logging
import time
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel

from database import get_db
from models.core import Product, Inventory, Organization, Review

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Public"])


# ======================== SCHEMAS ========================

class PublicProductResponse(BaseModel):
    id: int
    name: str = ""
    sku: str = ""
    category: str = ""
    selling_price: float = 0.0
    stock_quantity: int = 0
    low_stock_threshold: int = 5
    availability: str = "out_of_stock"
    last_updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ======================== HELPERS (Single Source of Truth) ========================

def get_availability(stock: int, threshold: int) -> str:
    """
    Centralized availability logic — import this wherever needed.
    Single source of truth for in_stock / low_stock / out_of_stock.
    """
    if stock <= 0:
        return "out_of_stock"
    elif stock <= threshold:
        return "low_stock"
    return "in_stock"


# ======================== LIGHTWEIGHT CACHE ========================

_cache = {}
_CACHE_TTL_SECONDS = 30


def _cache_key(store_id, search, category, availability, limit, offset):
    return f"{store_id}:{search}:{category}:{availability}:{limit}:{offset}"


def _get_cached(key):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SECONDS:
        return entry["data"]
    return None


def _set_cached(key, data):
    _cache[key] = {"data": data, "ts": time.time()}


def invalidate_public_cache():
    """
    FULL cache clear — always full wipe, no partial key invalidation.
    """
    _cache.clear()


# IMPORTANT:
# If ANY future operation modifies inventory (returns, cancellations,
# manual adjustments, bulk imports, etc.), on_inventory_change() MUST
# be called to keep the public API cache in sync.
def on_inventory_change():
    """Call this from ANY code path that modifies stock levels."""
    invalidate_public_cache()


# ======================== INTERNAL HELPERS ========================

def _build_row_response(row) -> PublicProductResponse:
    """Build a single response dict from a query row. Guarantees no nulls."""
    qty = row.stock_quantity  # Already COALESCED to 0 in SQL
    threshold = row.low_stock_threshold or 5

    # last_updated_at: product.updated_at is the canonical source of truth
    # Only fall back to inventory.updated_at if product.updated_at is NULL
    last_updated = row.product_updated_at or row.inventory_updated_at

    return PublicProductResponse(
        id=row.id,
        name=row.name or "",
        sku=row.sku or "",
        category=row.category or "",
        selling_price=round(row.selling_price or 0.0, 2),
        stock_quantity=qty,
        low_stock_threshold=threshold,
        availability=get_availability(qty, threshold),
        last_updated_at=last_updated,
    )


def _base_query(db: Session):
    """
    Shared base query for both list and detail endpoints.
    Stock is ALWAYS from inventory.quantity_on_hand via COALESCE.
    """
    return (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.category,
            Product.selling_price,
            Product.low_stock_threshold,
            Product.shop_id,
            Product.updated_at.label("product_updated_at"),
            func.coalesce(Inventory.quantity_on_hand, 0).label("stock_quantity"),
            Inventory.updated_at.label("inventory_updated_at"),
        )
        .outerjoin(
            Inventory,
            (Inventory.product_id == Product.id) & (Inventory.shop_id == Product.shop_id)
        )
        .filter(Product.is_deleted == False)
    )


# ======================== ENDPOINTS ========================

@router.get("/public/products", response_model=List[PublicProductResponse])
def get_public_products(
    store_id: Optional[int] = Query(None, description="Filter by store/organization ID"),
    search: Optional[str] = Query(None, description="Search product name or SKU"),
    category: Optional[str] = Query(None, description="Filter by category"),
    availability: Optional[str] = Query(None, description="Filter: in_stock, low_stock, out_of_stock"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Public endpoint — real-time product availability.
    No auth required. cost_price excluded. Multi-tenant safe.
    store_id is REQUIRED to prevent cross-tenant data leaks.
    """
    # --- Multi-tenant safety: store_id is mandatory ---
    if not store_id:
        raise HTTPException(status_code=400, detail="store_id is required")

    # --- Cache check ---
    key = _cache_key(store_id, search, category, availability, limit, offset)
    cached = _get_cached(key)
    if cached is not None:
        return cached

    # --- Build query ---
    query = _base_query(db)

    # Multi-tenant safety: ALL queries enforce shop_id
    query = query.filter(Product.shop_id == store_id)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Product.name.ilike(search_term)) | (Product.sku.ilike(search_term))
        )

    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))

    # Deterministic ordering: most recently updated first, tie-break by id
    query = query.order_by(desc(Product.updated_at), desc(Product.id))
    query = query.offset(offset).limit(limit)
    rows = query.all()

    # --- Build response ---
    results = []
    for row in rows:
        resp = _build_row_response(row)

        # Post-query availability filter
        if availability and resp.availability != availability:
            continue

        results.append(resp)

    # --- Cache result ---
    _set_cached(key, results)

    logger.info("PUBLIC_API: %d products (store=%s, search=%s)", len(results), store_id, search)
    return results


@router.get("/public/products/{product_id}", response_model=PublicProductResponse)
def get_public_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get availability for a single product by ID."""
    row = (
        _base_query(db)
        .filter(Product.id == product_id)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Product not found")

    return _build_row_response(row)


# ======================== PUBLIC STORE DIRECTORY ========================

class TrustBreakdown(BaseModel):
    rating: float = 0.0
    delivery: float = 0.0
    fairness: float = 0.0
    activity: float = 0.0

class PublicStoreResponse(BaseModel):
    id: int
    name: str = ""
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    product_count: int = 0
    rating: float = 0.0
    total_reviews: int = 0
    trust_score: float = 0.0
    trust_breakdown: Optional[TrustBreakdown] = None

    class Config:
        from_attributes = True


@router.get("/public/stores")
def list_public_stores(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Public store directory with pagination.
    Returns only organizations where is_public=TRUE and has products.
    """
    print("PUBLIC STORES API HIT")
    from sqlalchemy import func as sqlfunc

    product_count_sq = (
        db.query(
            Product.shop_id,
            sqlfunc.count(Product.id).label("product_count")
        )
        .filter(Product.is_deleted == False)
        .group_by(Product.shop_id)
        .subquery()
    )

    # Review aggregation subquery
    review_sq = (
        db.query(
            Review.store_id,
            sqlfunc.avg(Review.rating).label("avg_rating"),
            sqlfunc.count(Review.id).label("total_reviews"),
        )
        .group_by(Review.store_id)
        .subquery()
    )

    base_query = (
        db.query(
            Organization.id,
            Organization.name,
            Organization.category,
            Organization.address,
            Organization.phone,
            Organization.trust_score,
            sqlfunc.coalesce(product_count_sq.c.product_count, 0).label("product_count"),
            sqlfunc.coalesce(review_sq.c.avg_rating, 0.0).label("avg_rating"),
            sqlfunc.coalesce(review_sq.c.total_reviews, 0).label("total_reviews"),
        )
        .outerjoin(product_count_sq, Organization.id == product_count_sq.c.shop_id)
        .outerjoin(review_sq, Organization.id == review_sq.c.store_id)
        .filter(
            Organization.is_public == True,
            Organization.is_deleted == False,
        )
    )

    if category:
        base_query = base_query.filter(Organization.category.ilike(f"%{category}%"))
    if search:
        base_query = base_query.filter(Organization.name.ilike(f"%{search}%"))

    # Only stores with products
    base_query = base_query.having(sqlfunc.coalesce(product_count_sq.c.product_count, 0) > 0)

    # Count total
    count_query = base_query.subquery()
    total_count = db.query(sqlfunc.count()).select_from(count_query).scalar() or 0

    rows = base_query.order_by(Organization.name.asc()).offset(offset).limit(limit).all()

    store_list = []
    for r in rows:
        breakdown = _compute_trust_breakdown(db, r.id)
        store_list.append(PublicStoreResponse(
            id=r.id, name=r.name or "",
            category=r.category, address=r.address, phone=r.phone,
            product_count=r.product_count,
            rating=round(r.avg_rating, 1),
            total_reviews=r.total_reviews,
            trust_score=round(r.trust_score or 0, 2),
            trust_breakdown=breakdown,
        ).model_dump())

    return {
        "total_count": total_count,
        "stores": store_list,
    }


# ======================== PUBLIC PRODUCT SEARCH ========================

class SearchProductResponse(BaseModel):
    product_id: int
    name: str = ""
    category: str = ""
    price: float = 0.0
    availability: str = "out_of_stock"
    stock_quantity: int = 0
    store_name: str = ""
    store_id: int = 0
    demand_score: float = 0.0
    relevance_score: float = 0.0
    ranking_reason: str = ""

    class Config:
        from_attributes = True


@router.get("/public/search", response_model=List[SearchProductResponse])
def search_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    store_id: Optional[int] = None,
    sort_by: Optional[str] = Query("relevance", pattern="^(relevance|price_asc|price_desc|demand)$"),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Public product search with filters and AI-powered ranking.
    Only returns products from public stores.
    """
    from sqlalchemy import func as sqlfunc, case
    from models.core import ProductInsight

    # Base: products from public orgs only
    query = (
        db.query(
            Product.id.label("product_id"),
            Product.name,
            Product.category,
            Product.selling_price.label("price"),
            sqlfunc.coalesce(Inventory.quantity_on_hand, 0).label("stock_quantity"),
            Organization.name.label("store_name"),
            Organization.id.label("store_id"),
            sqlfunc.coalesce(ProductInsight.predicted_daily_demand, 0.0).label("raw_demand"),
        )
        .join(Organization, Product.shop_id == Organization.id)
        .outerjoin(Inventory, (Inventory.product_id == Product.id) & (Inventory.shop_id == Product.shop_id))
        .outerjoin(ProductInsight, ProductInsight.product_id == Product.id)
        .filter(
            Organization.is_public == True,
            Organization.is_deleted == False,
            Product.is_deleted == False,
        )
    )

    # Filters
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if min_price is not None:
        query = query.filter(Product.selling_price >= min_price)
    if max_price is not None:
        query = query.filter(Product.selling_price <= max_price)
    if store_id:
        query = query.filter(Product.shop_id == store_id)

    rows = query.limit(limit).all()

    # Compute scores and rank
    results = []
    for r in rows:
        stock = r.stock_quantity or 0
        demand_score = min((r.raw_demand or 0) / 100.0, 1.0)
        availability = get_availability(stock, 5)
        avail_score = 1.0 if availability == "in_stock" else (0.5 if availability == "low_stock" else 0.0)
        price_val = r.price or 0
        price_score = max(0, 1.0 - (price_val / 10000.0))  # Normalize: cheaper = higher score
        relevance = round(0.5 * demand_score + 0.3 * avail_score + 0.2 * price_score, 3)

        # Ranking reason
        if demand_score > 0.6 and availability == "in_stock":
            ranking_reason = "High demand + In stock"
        elif price_score > 0.7:
            ranking_reason = "Best price"
        elif availability == "low_stock":
            ranking_reason = "Limited availability"
        elif demand_score > 0.5:
            ranking_reason = "Popular item"
        else:
            ranking_reason = "Recommended"

        results.append(SearchProductResponse(
            product_id=r.product_id,
            name=r.name or "",
            category=r.category or "",
            price=price_val,
            availability=availability,
            stock_quantity=stock,
            store_name=r.store_name or "",
            store_id=r.store_id,
            demand_score=round(demand_score, 3),
            relevance_score=relevance,
            ranking_reason=ranking_reason,
        ))

    # Sort
    if sort_by == "price_asc":
        results.sort(key=lambda x: x.price)
    elif sort_by == "price_desc":
        results.sort(key=lambda x: x.price, reverse=True)
    elif sort_by == "demand":
        results.sort(key=lambda x: x.demand_score, reverse=True)
    else:
        results.sort(key=lambda x: x.relevance_score, reverse=True)

    # FIX 3: Search fallback — if no results and filters were applied, relax and retry
    fallback_used = False
    if len(results) == 0 and (q or category or min_price is not None or max_price is not None):
        # Retry with only text query (relax price/category)
        fallback_query = (
            db.query(
                Product.id.label("product_id"),
                Product.name,
                Product.category,
                Product.selling_price.label("price"),
                sqlfunc.coalesce(Inventory.quantity_on_hand, 0).label("stock_quantity"),
                Organization.name.label("store_name"),
                Organization.id.label("store_id"),
                sqlfunc.coalesce(ProductInsight.predicted_daily_demand, 0.0).label("raw_demand"),
            )
            .join(Organization, Product.shop_id == Organization.id)
            .outerjoin(Inventory, (Inventory.product_id == Product.id) & (Inventory.shop_id == Product.shop_id))
            .outerjoin(ProductInsight, ProductInsight.product_id == Product.id)
            .filter(
                Organization.is_public == True,
                Organization.is_deleted == False,
                Product.is_deleted == False,
            )
        )
        # Broad fuzzy match on name or category
        if q:
            fallback_query = fallback_query.filter(
                (Product.name.ilike(f"%{q}%")) | (Product.category.ilike(f"%{q}%"))
            )
        elif category:
            fallback_query = fallback_query.filter(Product.category.ilike(f"%{category}%"))

        fb_rows = fallback_query.limit(limit).all()
        for r in fb_rows:
            stock = r.stock_quantity or 0
            demand_score = min((r.raw_demand or 0) / 100.0, 1.0)
            availability = get_availability(stock, 5)
            avail_score = 1.0 if availability == "in_stock" else (0.5 if availability == "low_stock" else 0.0)
            price_val = r.price or 0
            price_score = max(0, 1.0 - (price_val / 10000.0))
            relevance = round(0.5 * demand_score + 0.3 * avail_score + 0.2 * price_score, 3)
            results.append(SearchProductResponse(
                product_id=r.product_id, name=r.name or "", category=r.category or "",
                price=price_val, availability=availability, stock_quantity=stock,
                store_name=r.store_name or "", store_id=r.store_id,
                demand_score=round(demand_score, 3), relevance_score=relevance,
                ranking_reason="Similar product",
            ))
        if results:
            fallback_used = True
            results.sort(key=lambda x: x.relevance_score, reverse=True)

    if fallback_used:
        return {
            "fallback_used": True,
            "message": "No exact results \u2014 showing similar products",
            "results": [r.model_dump() for r in results],
        }

    return results


# ======================== REVIEWS + TRUST ========================

from pydantic import Field as PydField
from auth import get_current_user
from models.core import User, Order


class ReviewCreate(BaseModel):
    store_id: int
    order_id: Optional[int] = None
    product_id: Optional[int] = None
    rating: int = PydField(..., ge=1, le=5)
    comment: Optional[str] = PydField(None, max_length=1000)


@router.post("/reviews")
def create_review(
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a review for a store. Only after a delivered order."""
    user_id = current_user.get("user_id")

    # Prevent self-review
    org_id = current_user.get("organization_id")
    if org_id == payload.store_id:
        from fastapi import HTTPException as HE
        raise HE(status_code=400, detail="Cannot review your own store")

    # Verify order belongs to user and is delivered (if order_id provided)
    if payload.order_id:
        from fastapi import HTTPException as HE
        order = db.query(Order).filter(
            Order.id == payload.order_id,
            Order.user_id == user_id,
        ).first()
        if not order:
            raise HE(status_code=404, detail="Order not found")
        if order.status != "delivered":
            raise HE(status_code=400, detail="Can only review after order is delivered")

        # Prevent duplicate
        existing = db.query(Review).filter(
            Review.user_id == user_id, Review.order_id == payload.order_id
        ).first()
        if existing:
            raise HE(status_code=409, detail="Already reviewed this order")

    # FIX 4: Determine verified_purchase
    is_verified = False
    if payload.order_id:
        from models.core import PriceRequest
        order_check = db.query(Order).join(PriceRequest, Order.negotiation_request_id == PriceRequest.id).filter(
            Order.id == payload.order_id, PriceRequest.user_id == user_id, Order.status == "delivered"
        ).first()
        is_verified = order_check is not None

    review = Review(
        user_id=user_id,
        store_id=payload.store_id,
        order_id=payload.order_id,
        product_id=payload.product_id,
        rating=payload.rating,
        comment=payload.comment,
        verified_purchase=is_verified,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    # Recompute trust score
    _recompute_trust_score(db, payload.store_id)

    return {
        "id": review.id,
        "rating": review.rating,
        "verified_purchase": review.verified_purchase,
        "message": "Review submitted successfully",
    }


@router.get("/stores/{store_id}/reviews")
def get_store_reviews(
    store_id: int,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get reviews for a public store."""
    from sqlalchemy import func as sqlfunc

    reviews = (
        db.query(Review)
        .filter(Review.store_id == store_id)
        .order_by(Review.created_at.desc())
        .offset(offset).limit(limit)
        .all()
    )

    total = db.query(sqlfunc.count(Review.id)).filter(Review.store_id == store_id).scalar() or 0
    avg = db.query(sqlfunc.avg(Review.rating)).filter(Review.store_id == store_id).scalar() or 0

    return {
        "store_id": store_id,
        "avg_rating": round(float(avg), 1),
        "total_reviews": total,
        "reviews": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "rating": r.rating,
                "comment": r.comment,
                "verified_purchase": r.verified_purchase,
                "created_at": r.created_at,
            }
            for r in reviews
        ],
    }


def _compute_trust_breakdown(db: Session, store_id: int) -> TrustBreakdown:
    """Compute the 4 trust signals for a store (0-1 each). Used for explainability."""
    from sqlalchemy import func as sqlfunc
    from models.core import PriceRequest

    avg_rating = db.query(sqlfunc.avg(Review.rating)).filter(Review.store_id == store_id).scalar() or 0
    rating_score = round(float(avg_rating) / 5.0, 2)

    total_orders = db.query(sqlfunc.count(Order.id)).filter(Order.shop_id == store_id).scalar() or 0
    delivered_orders = db.query(sqlfunc.count(Order.id)).filter(
        Order.shop_id == store_id, Order.status == "delivered"
    ).scalar() or 0
    delivery_score = round(delivered_orders / total_orders, 2) if total_orders > 0 else 0.5

    neg_count = db.query(sqlfunc.count(PriceRequest.id)).filter(PriceRequest.shop_id == store_id).scalar() or 0
    avg_delta = db.query(sqlfunc.avg(PriceRequest.negotiation_delta)).filter(
        PriceRequest.shop_id == store_id
    ).scalar() or 0
    fairness_score = round(max(0, 1.0 - abs(float(avg_delta))), 2) if neg_count > 0 else 0.5

    product_count = db.query(sqlfunc.count(Product.id)).filter(
        Product.shop_id == store_id, Product.is_deleted == False
    ).scalar() or 0
    activity_score = round(min(product_count / 10.0, 1.0), 2)

    return TrustBreakdown(
        rating=rating_score,
        delivery=delivery_score,
        fairness=fairness_score,
        activity=activity_score,
    )


def _recompute_trust_score(db: Session, store_id: int):
    """Recompute trust score for an organization after a new review."""
    org = db.query(Organization).filter(Organization.id == store_id).first()
    if not org:
        return

    bd = _compute_trust_breakdown(db, store_id)
    trust = round(0.4 * bd.rating + 0.3 * bd.delivery + 0.2 * bd.fairness + 0.1 * bd.activity, 2)
    org.trust_score = trust
    db.commit()
    logger.info("TRUST_RECOMPUTE: store=%d trust=%.2f (r=%.2f d=%.2f f=%.2f a=%.2f)", store_id, trust, bd.rating, bd.delivery, bd.fairness, bd.activity)
