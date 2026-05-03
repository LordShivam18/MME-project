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
    is_public = Column(Boolean, default=False, nullable=False, server_default="false")
    category = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    trust_score = Column(Float, default=0.0, nullable=False, server_default="0.0")
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
    username = Column(String, unique=True, index=True, nullable=True)
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)  # nullable for OAuth-only users
    hashed_refresh_token = Column(String, nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=True)
    role = Column(String, default="admin", nullable=False, server_default="admin")
    business_type = Column(String, default="customer", nullable=False, server_default="customer")
    kyc_complete = Column(Boolean, default=False, nullable=False, server_default="false")
    is_platform_admin = Column(Boolean, default=False, nullable=False, server_default="false")
    token_version = Column(Integer, default=0, nullable=False, server_default="0")
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="false")
    last_blocked_at = Column(DateTime, nullable=True)
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
    low_stock_threshold = Column(Integer, default=5, nullable=False, server_default="5")
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
    reserved_quantity = Column(Integer, default=0, nullable=False, server_default="0")
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

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, default=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)

    # Relationships
    organization = relationship("Organization")
    contact = relationship("Contact")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True, nullable=False)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(String(2048), nullable=False)
    is_read = Column(Boolean, default=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")

class OTPCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    hashed_otp = Column(String, nullable=False)
    purpose = Column(String, nullable=False)  # signup, forgot_password
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    
    # Adaptive AI Upgrades
    bias_factor = Column(Float, default=0.0)
    adaptive_alpha = Column(Float, default=0.3)
    priority_score = Column(Float, default=0.0)
    priority_demand_norm = Column(Float, default=0.0)
    priority_margin_norm = Column(Float, default=0.0)
    priority_risk_norm = Column(Float, default=0.0)
    
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
    contact_id = Column(Integer, ForeignKey("contacts.id"), index=True, nullable=True)  # nullable for negotiation orders
    negotiation_request_id = Column(Integer, ForeignKey("price_requests.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True) # Buyer who placed the order
    
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


# ============================================================
# PRICING ENGINE MODELS
# ============================================================

class PricingTier(Base):
    __tablename__ = "pricing_tiers"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    shop_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    min_qty = Column(Integer, nullable=False)
    price_per_unit = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    product = relationship("Product")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint('product_id', 'min_qty', name='uix_product_min_qty'),
    )


class PriceRequest(Base):
    __tablename__ = "price_requests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    shop_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    requested_price = Column(Float, nullable=False)
    approved_price = Column(Float, nullable=True)
    status = Column(String, default="pending", nullable=False, server_default="pending")
    admin_note = Column(String, nullable=True)
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    negotiation_delta = Column(Float, nullable=True)  # (bulk - approved) / bulk
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    product = relationship("Product")
    organization = relationship("Organization")

    __table_args__ = (
        CheckConstraint("status IN ('pending','accepted','rejected')", name='ck_price_request_status'),
        Index('ix_price_requests_user_product', 'user_id', 'product_id'),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key = Column(String, nullable=False)
    response_json = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'key', name='uix_user_idempotency_key'),
    )


class UserKYC(Base):
    __tablename__ = "user_kyc"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=False)
    address = Column(String, nullable=True)
    business_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User")


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(String(1000), nullable=True)
    verified_purchase = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint('user_id', 'order_id', name='uix_user_order_review'),
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False) # The buyer who created it
    order_id = Column(Integer, ForeignKey("orders.id"), index=True, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False) # For seller isolation
    issue_type = Column(String, nullable=False) # refund/damaged/wrong_item/other
    status = Column(String, default="open", nullable=False) # open/in_progress/resolved
    priority = Column(String, default="medium", nullable=False) # low/medium/high
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    # Relationships
    order = relationship("Order")
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization")
    messages = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan")
    events = relationship("TicketEvent", back_populates="ticket", cascade="all, delete-orphan")

class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id"), index=True, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False) # User ID of whoever sent it
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User")

class TicketEvent(Base):
    __tablename__ = "ticket_events"
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id"), index=True, nullable=False)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("SupportTicket", back_populates="events")
    user = relationship("User")
