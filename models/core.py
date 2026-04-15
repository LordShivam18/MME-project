from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, CheckConstraint, text, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="organization")
    products = relationship("Product", back_populates="organization")
    inventory = relationship("Inventory", back_populates="organization")
    sales = relationship("Sale", back_populates="organization")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    hashed_refresh_token = Column(String, nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

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

    # Relationships
    organization = relationship("Organization", back_populates="sales")
