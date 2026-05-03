"""
Public API — No authentication required.
Exposes real-time inventory availability for storefront consumption.
"""

import logging
import time
from typing import Optional, List
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from database import get_db
from models.core import Product, Inventory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Public"])


# ======================== SCHEMAS ========================

class PublicProductResponse(BaseModel):
    id: int
    name: str
    sku: Optional[str] = ""
    category: Optional[str] = ""
    selling_price: float = 0.0
    stock_quantity: int = 0
    low_stock_threshold: int = 5
    availability: str = "out_of_stock"  # "in_stock" | "low_stock" | "out_of_stock"
    last_updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ======================== HELPERS (Single Source of Truth) ========================

def get_availability(stock: int, threshold: int) -> str:
    """
    Centralized availability logic — used everywhere.
    Import this from routers.public wherever needed.
    """
    if stock <= 0:
        return "out_of_stock"
    elif stock <= threshold:
        return "low_stock"
    return "in_stock"


# ======================== LIGHTWEIGHT CACHE ========================
# Simple in-memory TTL cache for public product lists.
# No Redis needed — just a dict with a timestamp.

_cache = {}
_CACHE_TTL_SECONDS = 30  # 30-second TTL


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
    """Call this whenever stock changes to clear the cache."""
    _cache.clear()


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
    Public endpoint — returns real-time product availability.
    No authentication required. Sensitive fields (cost_price) are excluded.
    Stock is always derived from inventory.quantity_on_hand (single source of truth).
    """
    # Check cache
    key = _cache_key(store_id, search, category, availability, limit, offset)
    cached = _get_cached(key)
    if cached is not None:
        logger.debug("PUBLIC_API: cache hit for key=%s", key)
        return cached

    # Base query: products LEFT JOIN inventory
    # Stock is ALWAYS from inventory.quantity_on_hand via COALESCE
    query = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.category,
            Product.selling_price,
            Product.low_stock_threshold,
            Product.updated_at,
            Product.shop_id,
            func.coalesce(Inventory.quantity_on_hand, 0).label("stock_quantity"),
            Inventory.updated_at.label("inventory_updated_at"),
        )
        .outerjoin(Inventory, (Inventory.product_id == Product.id) & (Inventory.shop_id == Product.shop_id))
        .filter(Product.is_deleted == False)
    )

    # Filters
    if store_id:
        query = query.filter(Product.shop_id == store_id)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Product.name.ilike(search_term)) | (Product.sku.ilike(search_term))
        )

    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))

    # Execute
    query = query.order_by(Product.name).offset(offset).limit(limit)
    rows = query.all()

    # Build response — no null fields
    results = []
    for row in rows:
        qty = row.stock_quantity  # Already COALESCED to 0
        threshold = row.low_stock_threshold or 5
        avail = get_availability(qty, threshold)

        # Post-query availability filter
        if availability and avail != availability:
            continue

        last_updated = row.inventory_updated_at or row.updated_at

        results.append(PublicProductResponse(
            id=row.id,
            name=row.name or "",
            sku=row.sku or "",
            category=row.category or "",
            selling_price=row.selling_price or 0.0,
            stock_quantity=qty,
            low_stock_threshold=threshold,
            availability=avail,
            last_updated_at=last_updated,
        ))

    # Cache result
    _set_cached(key, results)

    logger.info("PUBLIC_API: returned %d products (store_id=%s, search=%s)", len(results), store_id, search)
    return results


@router.get("/public/products/{product_id}", response_model=PublicProductResponse)
def get_public_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get availability for a single product by ID."""
    row = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.category,
            Product.selling_price,
            Product.low_stock_threshold,
            Product.updated_at,
            func.coalesce(Inventory.quantity_on_hand, 0).label("stock_quantity"),
            Inventory.updated_at.label("inventory_updated_at"),
        )
        .outerjoin(Inventory, (Inventory.product_id == Product.id) & (Inventory.shop_id == Product.shop_id))
        .filter(Product.id == product_id, Product.is_deleted == False)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Product not found")

    qty = row.stock_quantity
    threshold = row.low_stock_threshold or 5

    return PublicProductResponse(
        id=row.id,
        name=row.name or "",
        sku=row.sku or "",
        category=row.category or "",
        selling_price=row.selling_price or 0.0,
        stock_quantity=qty,
        low_stock_threshold=threshold,
        availability=get_availability(qty, threshold),
        last_updated_at=row.inventory_updated_at or row.updated_at,
    )
