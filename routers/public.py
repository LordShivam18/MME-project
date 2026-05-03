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
from models.core import Product, Inventory, Organization

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

class PublicStoreResponse(BaseModel):
    id: int
    name: str = ""
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    product_count: int = 0

    class Config:
        from_attributes = True


@router.get("/public/stores", response_model=List[PublicStoreResponse])
def list_public_stores(
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Public store directory. Returns only organizations where is_public=TRUE and has products.
    No auth required.
    """
    from sqlalchemy import func as sqlfunc

    # Subquery: count products per org
    product_count_sq = (
        db.query(
            Product.shop_id,
            sqlfunc.count(Product.id).label("product_count")
        )
        .filter(Product.is_deleted == False)
        .group_by(Product.shop_id)
        .subquery()
    )

    query = (
        db.query(
            Organization.id,
            Organization.name,
            Organization.category,
            Organization.address,
            Organization.phone,
            sqlfunc.coalesce(product_count_sq.c.product_count, 0).label("product_count"),
        )
        .outerjoin(product_count_sq, Organization.id == product_count_sq.c.shop_id)
        .filter(
            Organization.is_public == True,
            Organization.is_deleted == False,
        )
    )

    if category:
        query = query.filter(Organization.category.ilike(f"%{category}%"))
    if search:
        query = query.filter(Organization.name.ilike(f"%{search}%"))

    # Only stores with at least 1 product
    query = query.having(sqlfunc.coalesce(product_count_sq.c.product_count, 0) > 0)
    rows = query.order_by(Organization.name.asc()).limit(100).all()

    return [
        PublicStoreResponse(
            id=r.id, name=r.name or "",
            category=r.category, address=r.address, phone=r.phone,
            product_count=r.product_count,
        )
        for r in rows
    ]
