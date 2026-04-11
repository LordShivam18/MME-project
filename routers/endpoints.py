from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
import logging
import os
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

from database import get_db
from models import core as models
from schemas import core as schemas
from services.prediction_service import get_product_prediction, invalidate_prediction_cache
from limiter import limiter
from auth import get_current_user
from fastapi.security import OAuth2PasswordRequestForm

logger = logging.getLogger(__name__)
router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_dev_key")

# --- Auth Endpoints ---
@router.post("/auth/token")
@limiter.limit("10/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    logger.info("User lookup executed")
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    if not user:
        logger.info("User not found")
        raise HTTPException(status_code=401, detail="Incorrect credentials")
        
    logger.info("User found")
    
    from auth import preprocess_password
    processed_pw = preprocess_password(form_data.password)
    
    if not pwd_context.verify(processed_pw, user.hashed_password):
        logger.warning("Password failed")
        raise HTTPException(status_code=401, detail="Incorrect credentials")
        
    logger.info("Password verified")
    
    # Generate actual JWT
    access_token = jwt.encode(
        {"sub": user.email, "user_id": user.id, "exp": datetime.utcnow() + timedelta(days=1)}, 
        SECRET_KEY, 
        algorithm="HS256"
    )
    
    logger.info("JWT token generated")
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/auth/me")
@limiter.limit("100/minute")
def validate_token(request: Request, current_user: dict = Depends(get_current_user)):
    return {"status": "ok", "user": current_user}

# --- Products CRUD ---
@router.post("/products/", response_model=schemas.ProductResponse)
@limiter.limit("100/minute")
def create_product(request: Request, product: schemas.ProductCreate, shop_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_product = models.Product(**product.model_dump(), shop_id=shop_id)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    
    db_inv = models.Inventory(shop_id=shop_id, product_id=db_product.id, quantity_on_hand=0)
    db.add(db_inv)
    db.commit()
    return db_product

@router.get("/products/", response_model=List[schemas.ProductResponse])
@limiter.limit("100/minute")
def read_products(request: Request, shop_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    products = db.query(models.Product).filter(models.Product.shop_id == shop_id).offset(skip).limit(limit).all()
    return products


# --- Sales Entry & Inventory Updater (ACID Transaction) ---
@router.post("/sales/", response_model=schemas.SalesResponse)
@limiter.limit("100/minute")
def log_sale(request: Request, sale: schemas.SalesCreate, shop_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        db_sale = models.SaleTransaction(**sale.model_dump(), shop_id=shop_id)
        db.add(db_sale)
        
        inventory = db.query(models.Inventory).filter(
            models.Inventory.shop_id == shop_id,
            models.Inventory.product_id == sale.product_id
        ).with_for_update().first()
        
        if not inventory:
            raise ValueError("Inventory not found.")
        if inventory.quantity_on_hand < sale.quantity_sold:
            raise ValueError("Insufficient inventory on hand.")
            
        inventory.quantity_on_hand -= sale.quantity_sold
        db.commit()
        db.refresh(db_sale)
        
        # KEY ADDITION: Invalidate Prediction Cache upon success
        invalidate_prediction_cache(shop_id, sale.product_id)
        
        return db_sale
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal Database Error.")


# --- Inventory Fetch ---
@router.get("/inventory/summary", response_model=List[schemas.InventorySummaryResponse])
@limiter.limit("50/minute")
def get_inventory_summary(request: Request, shop_id: int, limit: int = 100, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Highly optimized single DB join avoiding Promise.all API abuse
    joined_data = db.query(models.Product, models.Inventory).join(
        models.Inventory, models.Product.id == models.Inventory.product_id
    ).filter(
        models.Product.shop_id == shop_id,
        models.Inventory.shop_id == shop_id
    ).limit(limit).all()
    
    summary = []
    for product, inventory in joined_data:
        summary.append({
            "product_id": product.id,
            "name": product.name,
            "sku": product.sku,
            "category": product.category,
            "base_price": product.base_price,
            "quantity_on_hand": inventory.quantity_on_hand,
            "reorder_point": inventory.reorder_point
        })
    return summary

@router.get("/inventory/{product_id}", response_model=schemas.InventoryResponse)
@limiter.limit("100/minute")
def get_inventory(request: Request, shop_id: int, product_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    inventory = db.query(models.Inventory).filter(
        models.Inventory.shop_id == shop_id,
        models.Inventory.product_id == product_id
    ).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Not found")
    return inventory


# --- Read-Only Prediction Output (TIGHTLY LIMITED) ---
@router.get("/predictions/{product_id}", response_model=schemas.PredictionResponse)
@limiter.limit("20/minute") # Strict 20 req/min specifically to prevent computational spam
def get_prediction_insights(request: Request, shop_id: int, product_id: int, window_size_days: int = 14, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        prediction = get_product_prediction(db, shop_id=shop_id, product_id=product_id, window_size=window_size_days)
        return prediction
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
