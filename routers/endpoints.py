from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
import logging
import os
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

from database import get_db
from models import core as models
from schemas import core as schemas
# from services.prediction_service import get_product_prediction, invalidate_prediction_cache
from limiter import limiter
from auth import get_current_user
from fastapi.security import OAuth2PasswordRequestForm

logger = logging.getLogger(__name__)
router = APIRouter()

from auth import pwd_context
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
    
    if not pwd_context.verify(form_data.password, user.hashed_password):
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
def create_product(request: Request, product: schemas.ProductCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # NOTE: Extrapolating into an object fallback to strictly enforce requested assignment logic without triggering Dictionary assignment aborts locally in production overrides.
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get("user_id")
    
    print("Creating product for user:", user_id)
    print("Product data:", product.model_dump())
    
    sku_exists = db.query(models.Product).filter(
        models.Product.sku == product.sku,
        models.Product.shop_id == user_id
    ).first()

    if sku_exists:
        raise HTTPException(status_code=400, detail="Product with this SKU already exists")
    
    try:
        new_product = models.Product(**product.model_dump())
        new_product.shop_id = user_id
        db.add(new_product)
        db.flush() # Locks generation sequence cleanly without terminating bounds
        
        # Synchronize Inventory Tracker natively onto the identical transaction pipeline
        db_inv = models.Inventory(shop_id=user_id, product_id=new_product.id, quantity_on_hand=0)
        db.add(db_inv)
        
        db.commit()
        db.refresh(new_product)
        return new_product
    except Exception as e:
        db.rollback()
        print("DB ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/products/", response_model=List[schemas.ProductResponse])
@limiter.limit("100/minute")
def read_products(request: Request, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    shop_id = current_user.get("user_id", 1)
    products = db.query(models.Product).filter(models.Product.shop_id == shop_id).offset(skip).limit(limit).all()
    return products


# --- Sales Entry & Inventory Updater (ACID Transaction) ---
@router.post("/sales/")
def record_sale(payload: schemas.SalesCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get("user_id")

    product = db.query(models.Product).filter_by(
        id=payload.product_id,
        shop_id=user_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    inventory = db.query(models.Inventory).filter_by(
        product_id=payload.product_id,
        shop_id=user_id
    ).first()

    if not inventory:
        inventory = models.Inventory(
            product_id=payload.product_id,
            shop_id=user_id,
            quantity_on_hand=0
        )
        db.add(inventory)
        db.commit()
        db.refresh(inventory)

    if inventory.quantity_on_hand < payload.quantity_sold:
        raise HTTPException(status_code=400, detail="Not enough stock")

    inventory.quantity_on_hand -= payload.quantity_sold

    sale = models.Sale(
        product_id=payload.product_id,
        shop_id=user_id,
        quantity_sold=payload.quantity_sold
    )

    db.add(sale)
    db.commit()

    return {"message": "Sale recorded!", "stock_left": inventory.quantity_on_hand}


# --- Inventory Fetch & Modification ---
@router.post("/inventory/add-stock")
def add_stock(payload: schemas.AddStockRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get("user_id")
    
    inventory = db.query(models.Inventory).filter_by(
        product_id=payload.product_id,
        shop_id=user_id
    ).first()

    if not inventory:
        inventory = models.Inventory(
            product_id=payload.product_id,
            shop_id=user_id,
            quantity_on_hand=payload.quantity
        )
        db.add(inventory)
    else:
        inventory.quantity_on_hand += payload.quantity

    db.commit()
    db.refresh(inventory)
    return {"message": "Stock updated successfully", "quantity_on_hand": inventory.quantity_on_hand}

@router.get("/inventory/summary", response_model=List[schemas.InventorySummaryResponse])
@limiter.limit("50/minute")
def get_inventory_summary(request: Request, limit: int = 100, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get("user_id")
    # Highly optimized single DB join avoiding Promise.all API abuse
    joined_data = db.query(models.Product, models.Inventory).join(
        models.Inventory, models.Product.id == models.Inventory.product_id
    ).filter(
        models.Product.shop_id == user_id,
        models.Inventory.shop_id == user_id
    ).limit(limit).all()
    
    summary = []
    for product, inventory in joined_data:
        summary.append({
            "product_id": product.id,
            "name": product.name,
            "sku": product.sku,
            "category": product.category,
            "selling_price": product.selling_price,
            "quantity_on_hand": inventory.quantity_on_hand,
            "reorder_point": inventory.reorder_point
        })
    return summary

@router.get("/inventory/{product_id}", response_model=schemas.InventoryResponse)
@limiter.limit("100/minute")
def get_inventory(request: Request, product_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get("user_id")
    inventory = db.query(models.Inventory).filter(
        models.Inventory.shop_id == user_id,
        models.Inventory.product_id == product_id
    ).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Not found")
    return inventory

@router.put("/products/{product_id}")
def update_product(product_id: int, updated: schemas.ProductCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get("user_id")
    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.shop_id == user_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        # exclude_unset permits purely partial parameter application seamlessly.
        for key, value in updated.model_dump(exclude_unset=True).items():
            setattr(product, key, value)
        db.commit()
        db.refresh(product)
        return product
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Product with this SKU already exists")

@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get("user_id")
    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.shop_id == user_id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Manually cascade inventory and sales dependencies internally preventing Postgres Constraint Crashes
    db.query(models.Inventory).filter_by(product_id=product_id, shop_id=user_id).delete()
    db.query(models.Sale).filter_by(product_id=product_id, shop_id=user_id).delete()
    
    db.delete(product)
    db.commit()
    return {"message": "Product deleted"}

# --- Read-Only Prediction Output (TIGHTLY LIMITED) ---
@router.get("/predictions/{product_id}", response_model=schemas.PredictionResponse)
@limiter.limit("20/minute") # Strict 20 req/min specifically to prevent computational spam
def get_prediction_insights(request: Request, product_id: int, window_size_days: int = 14, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get("user_id")
    try:
        # prediction = get_product_prediction(db, shop_id=user_id, product_id=product_id, window_size=window_size_days)
        # return prediction
        pass
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
