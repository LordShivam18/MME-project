"""
Public API — No authentication required.
Exposes real-time inventory availability for storefront consumption.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.core import Product, Inventory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Public"])


# ======================== SCHEMAS ========================

class PublicProductResponse(BaseModel):
    id: int
    name: str
    sku: Optional[str] = None
    category: Optional[str] = None
    selling_price: Optional[float] = None
    stock_quantity: int
    low_stock_threshold: int
    availability: str  # "in_stock" | "low_stock" | "out_of_stock"
    last_updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ======================== HELPERS ========================

def _get_availability(qty: int, threshold: int) -> str:
    if qty <= 0:
        return "out_of_stock"
    elif qty <= threshold:
        return "low_stock"
    return "in_stock"


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
    """
    # Base query: join products with inventory
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
            Inventory.quantity_on_hand,
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

    # Build response
    results = []
    for row in rows:
        qty = row.quantity_on_hand or 0
        threshold = row.low_stock_threshold or 5
        avail = _get_availability(qty, threshold)

        # Apply availability filter post-query (simpler than SQL CASE filter)
        if availability and avail != availability:
            continue

        last_updated = row.inventory_updated_at or row.updated_at

        results.append(PublicProductResponse(
            id=row.id,
            name=row.name,
            sku=row.sku,
            category=row.category,
            selling_price=row.selling_price,
            stock_quantity=qty,
            low_stock_threshold=threshold,
            availability=avail,
            last_updated_at=last_updated,
        ))

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
            Inventory.quantity_on_hand,
            Inventory.updated_at.label("inventory_updated_at"),
        )
        .outerjoin(Inventory, (Inventory.product_id == Product.id) & (Inventory.shop_id == Product.shop_id))
        .filter(Product.id == product_id, Product.is_deleted == False)
        .first()
    )

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")

    qty = row.quantity_on_hand or 0
    threshold = row.low_stock_threshold or 5

    return PublicProductResponse(
        id=row.id,
        name=row.name,
        sku=row.sku,
        category=row.category,
        selling_price=row.selling_price,
        stock_quantity=qty,
        low_stock_threshold=threshold,
        availability=_get_availability(qty, threshold),
        last_updated_at=row.inventory_updated_at or row.updated_at,
    )
