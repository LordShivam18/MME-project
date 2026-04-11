from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, CheckConstraint, text, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
class Shop(Base):
    __tablename__ = "shops"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String, index=True)
    sku = Column(String, index=True)
    category = Column(String, index=True)
    cost_price = Column(Float)
    selling_price = Column(Float)
    lead_time_days = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('shop_id', 'sku', name='uix_shop_sku'),
    )

class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("users.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    quantity_on_hand = Column(Integer, default=0)
    reorder_point = Column(Integer, default=0)
    safety_stock = Column(Integer, default=0)
    last_restocked_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('shop_id', 'product_id', name='uix_shop_product'),
        CheckConstraint('quantity_on_hand >= 0', name='check_qty_on_hand_positive'),
    )

class SaleTransaction(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("users.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    quantity_sold = Column(Integer)
    sale_price = Column(Float)
    sale_date = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint('quantity_sold > 0', name='check_qty_sold_positive'),
        Index('idx_sales_shop_product_date', 'shop_id', 'product_id', text('sale_date DESC')),
        Index('idx_sales_product_date', 'product_id', text('sale_date DESC'))
    )
