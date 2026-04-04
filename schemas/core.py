from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# --- Product Schemas ---
class ProductBase(BaseModel):
    # Stricter character validations
    name: str = Field(..., min_length=2, max_length=100, example="Wireless Mouse")
    sku: str = Field(..., min_length=3, max_length=50, example="WM-001")
    category: str = Field(..., min_length=2, max_length=50, example="Electronics")
    
    # Numeric clamping to prevent DB integer/float overflow attacks
    cost_price: float = Field(..., gt=0, le=9999999.99, example=10.50)
    base_price: float = Field(..., gt=0, le=9999999.99, example=25.00)
    lead_time_days: int = Field(..., ge=1, le=365, example=5)

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int
    shop_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# --- Sales Schemas ---
class SalesCreate(BaseModel):
    product_id: int
    # Prevents pushing millions of items to integer overflow standard SQL fields
    quantity_sold: int = Field(..., gt=0, le=10000) 
    sale_price: float = Field(..., gt=0, le=9999999.99)
    sale_date: Optional[datetime] = None

class SalesResponse(SalesCreate):
    id: int
    shop_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# --- Inventory Schemas ---
class InventoryResponse(BaseModel):
    id: int
    shop_id: int
    product_id: int
    quantity_on_hand: int
    reorder_point: int
    safety_stock: int
    
    class Config:
        from_attributes = True

# --- Prediction Schemas ---
class PredictionResponse(BaseModel):
    product_id: int
    suggested_order_qty: float
    predicted_daily_demand: float
    safety_stock_required: float
    reorder_point: float
    current_inventory: int
    action_required: str
