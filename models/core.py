from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, CheckConstraint, text, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    stripe_customer_id = Column(String, nullable=True, unique=True, index=True)
    ai_decision_mode = Column(String, default="balanced", nullable=False, server_default="balanced")
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="organization")
    products = relationship("Product", back_populates="organization")
    inventory = relationship("Inventory", back_populates="organization")
    sales = relationship("Sale", back_populates="organization")
    subscription = relationship("Subscription", back_populates="organization", uselist=False)
    payments = relationship("Payment", back_populates="organization")
    stripe_events = relationship("StripeEvent", back_populates="organization")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    hashed_refresh_token = Column(String, nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=True)
    role = Column(String, default="admin", nullable=False, server_default="admin")
    token_version = Column(Integer, default=0, nullable=False, server_default="0")
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="users")


class Shop(Base):
    __tablename__ = "shops"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    name = Column(String, index=True)
    sku = Column(String, index=True)
    category = Column(String, index=True)
    cost_price = Column(Float)
    selling_price = Column(Float)
    lead_time_days = Column(Integer)
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="products")

    __table_args__ = (
        UniqueConstraint('shop_id', 'sku', name='uix_shop_sku'),
    )


class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    quantity_on_hand = Column(Integer, default=0)
    reorder_point = Column(Integer, default=0)
    safety_stock = Column(Integer, default=0)
    last_restocked_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="inventory")

    __table_args__ = (
        UniqueConstraint('shop_id', 'product_id', name='uix_shop_product'),
        CheckConstraint('quantity_on_hand >= 0', name='check_qty_on_hand_positive'),
    )


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    shop_id = Column(Integer, ForeignKey("organizations.id"))
    quantity_sold = Column(Integer)
    sale_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="sales")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    organization_id = Column(Integer, nullable=False, index=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_audit_org_created', 'organization_id', 'created_at'),
        Index('ix_audit_org_action', 'organization_id', 'action'),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, index=True, nullable=False)
    plan = Column(String, default="free", nullable=False, server_default="free")
    status = Column(String, default="active", nullable=False, server_default="active")
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="subscription")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    stripe_payment_intent_id = Column(String, nullable=True, unique=True)
    stripe_checkout_session_id = Column(String, nullable=True)
    amount = Column(Integer, nullable=True)  # in smallest currency unit (cents/paise)
    currency = Column(String, default="usd", nullable=True)
    status = Column(String, default="pending", nullable=False, server_default="pending")  # pending, succeeded, failed
    plan = Column(String, nullable=True)
    metadata_json = Column(String, nullable=True)  # JSON string for extra Stripe metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="payments")


class StripeEvent(Base):
    """Webhook idempotency table. Stores processed Stripe event IDs to prevent duplicate processing."""
    __tablename__ = "stripe_events"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, nullable=False, index=True)  # Stripe event ID (evt_...)
    event_type = Column(String, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=True)
    status = Column(String, default="processed", nullable=False)  # processed, failed
    details = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="stripe_events")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    message = Column(String, nullable=False)
    type = Column(String, nullable=False)  # low_stock, insight, system
    priority = Column(String, default="low", nullable=False)  # low, medium, high
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")

class ProductInsight(Base):
    __tablename__ = "product_insights"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), unique=True, index=True, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    insight = Column(String, nullable=False)
    recommended_action = Column(String, nullable=False)
    confidence_score = Column(Integer, nullable=False)
    predicted_daily_demand = Column(Float, nullable=False, default=0.0)
    
    # AI Engine Upgrades
    demand_min = Column(Float, default=0.0)
    demand_max = Column(Float, default=0.0)
    stockout_risk = Column(String, default="none")       # none, low, medium, high, critical
    overstock_risk = Column(String, default="none")      # none, low, medium, high
    is_dead_stock = Column(Boolean, default=False)
    anomaly_flags = Column(String, nullable=True)        # JSON string
    weekday_pattern = Column(String, nullable=True)      # JSON string
    product_behavior_profile = Column(String, default="standard")
    last_profile_updated_at = Column(DateTime, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    model_version = Column(String, default="1.0.0")

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    product = relationship("Product")
    organization = relationship("Organization")

class OrderAdjustment(Base):
    __tablename__ = "order_adjustments"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), index=True, nullable=False)
    suggested_qty = Column(Float, nullable=False)
    actual_qty = Column(Float, nullable=False)
    adjustment_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    product = relationship("Product")

# ============================================================
# CONTACTS & ORDERS
# ============================================================

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    type = Column(String, nullable=False)  # supplier, customer
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    orders = relationship("Order", back_populates="contact")

    __table_args__ = (
        UniqueConstraint('organization_id', 'phone', name='uix_org_phone'),
    )


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    contact_id = Column(Integer, ForeignKey("contacts.id"), index=True, nullable=False)
    
    status = Column(String, default="pending", nullable=False) # pending, confirmed, shipped, delivered, cancelled
    delivery_status = Column(String, nullable=True) # processing, in_transit, etc
    tracking_number = Column(String, nullable=True)
    
    total_amount = Column(Float, nullable=False, default=0.0)
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="false")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    contact = relationship("Contact", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), index=True, nullable=False)
    
    quantity = Column(Integer, nullable=False)
    price_at_time = Column(Float, nullable=False) # Server calculates this
    
    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True, nullable=False)
    
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    
    changed_at = Column(DateTime, default=datetime.utcnow)
    changed_by = Column(String, nullable=True)  # System, User email, etc.
    
    # Relationships
    order = relationship("Order")
