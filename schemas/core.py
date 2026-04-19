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
    selling_price: float = Field(..., gt=0, le=9999999.99, example=25.00)
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
    quantity_sold: int
    sale_date: Optional[datetime] = None

class SalesResponse(SalesCreate):
    id: int
    shop_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# --- Inventory Schemas ---
class AddStockRequest(BaseModel):
    product_id: int
    quantity: int

class InventoryResponse(BaseModel):
    id: int
    shop_id: int
    product_id: int
    quantity_on_hand: int
    reorder_point: int
    safety_stock: int
    
    class Config:
        from_attributes = True

class InventorySummaryResponse(BaseModel):
    product_id: int
    name: str
    sku: str
    category: str
    selling_price: float
    quantity_on_hand: int
    reorder_point: int
    
    class Config:
        from_attributes = True

# --- Prediction Schemas ---
class PredictionResponse(BaseModel):
    product_id: int
    insight: str
    recommended_action: str
    confidence_score: int
    predicted_daily_demand: float

    class Config:
        from_attributes = True

# --- Notification Schemas ---
class NotificationResponse(BaseModel):
    id: int
    organization_id: int
    message: str
    type: str
    priority: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class NotificationUpdate(BaseModel):
    is_read: bool


# --- CRM Contact Schemas ---
class ContactBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = None
    type: str = Field(..., description="supplier or customer")

class ContactCreate(ContactBase):
    pass

class ContactResponse(ContactBase):
    id: int
    organization_id: int
    is_deleted: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Order Schemas ---
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)

class OrderItemResponse(BaseModel):
    id: int
    order_id: int
    product_id: int
    quantity: int
    price_at_time: float

    # Include nested product name context for UI
    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    contact_id: int
    items: list[OrderItemCreate]

class OrderUpdateStatus(BaseModel):
    status: Optional[str] = None # pending, confirmed, shipped, delivered, cancelled
    delivery_status: Optional[str] = None
    tracking_number: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    organization_id: int
    contact_id: int
    status: str
    delivery_status: Optional[str] = None
    tracking_number: Optional[str] = None
    total_amount: float
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse] = []

    class Config:
        from_attributes = True
