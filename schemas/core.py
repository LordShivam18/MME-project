from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- Organization Schemas ---
class OrganizationResponse(BaseModel):
    id: int
    name: str
    ai_decision_mode: Optional[str] = "assisted"
    class Config:
        from_attributes = True

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
class UserBase(BaseModel):
    email: EmailStr
    username: Optional[str] = None
    role: str = "admin"

class UserCreate(UserBase):
    password: str
    organization_name: str

class UserResponse(UserBase):
    id: int
    organization_id: int
    is_platform_admin: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

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
from typing import Optional, List, Dict, Any

class PredictionResponse(BaseModel):
    product_id: int
    insight: str
    recommended_action: str
    confidence_score: int
    predicted_daily_demand: float
    current_stock_quantity: int = 0
    avg_daily_sales: float = 0.0
    last_order_quantity: int = 0
    reorder_suggestion_source: str = "AI Logic Engine"
    recommended_suppliers: List[Dict[str, Any]] = []

    # AI Engine Upgrades
    demand_min: float = 0.0
    demand_max: float = 0.0
    stockout_risk: str = "none"
    overstock_risk: str = "none"
    is_dead_stock: bool = False
    anomaly_flags: List[str] = []
    weekday_pattern: Dict[str, float] = {}
    product_behavior_profile: str = "standard"
    explanation_points: List[str] = []
    recommendation_text: str = ""
    
    # Adaptive AI Upgrades
    bias_factor: float = 0.0
    adaptive_alpha: float = 0.3
    priority_score: float = 0.0
    priority_demand_norm: float = 0.0
    priority_margin_norm: float = 0.0
    priority_risk_norm: float = 0.0
    
    raw_debug_data: Optional[Dict[str, Any]] = None
    generated_at: Optional[datetime] = None
    model_version: str = "1.0.0"

    model_config = {
        "protected_namespaces": (),
        "from_attributes": True
    }

class AIPerformanceResponse(BaseModel):
    last_30_days: Dict[str, float]
    all_time: Dict[str, float]

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
class OrganizationModeUpdate(BaseModel):
    ai_decision_mode: str

