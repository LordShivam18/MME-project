from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session, Query
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
import logging
import os
from datetime import datetime, timedelta
from pydantic import BaseModel
from functools import wraps
import json

from database import get_db, SessionLocal
from models import core as models
from schemas import core as schemas
from services.prediction_service import get_product_prediction, invalidate_prediction_cache
from routers.public import on_inventory_change
from limiter import limiter
from auth import get_current_user, pwd_context, create_access_token, create_refresh_token, decode_token, require_platform_admin
from fastapi.security import OAuth2PasswordRequestForm

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Pydantic schemas ---
class RefreshTokenRequest(BaseModel):
    refresh_token: str

class InviteRequest(BaseModel):
    email: str
    role: str = "staff"


# ============================================================
# CENTRALIZED ORG FILTER
# ============================================================
def org_filter(query: Query, model, current_user: dict, include_deleted: bool = False) -> Query:
    """
    Centralized organization filter. ALWAYS derive org from server-side token.
    Automatically excludes soft-deleted records unless include_deleted=True.
    """
    org_id = current_user.get("organization_id") or current_user.get("user_id")
    filtered = query.filter(model.shop_id == org_id)
    if not include_deleted and hasattr(model, 'is_deleted'):
        filtered = filtered.filter(model.is_deleted == False)
    return filtered


def _org_id(current_user: dict) -> int:
    """Extract organization_id from the current_user dict."""
    return current_user.get("organization_id") or current_user.get("user_id")


# ============================================================
# RBAC PERMISSION CHECK
# ============================================================
def require_role(current_user: dict, allowed_roles: list):
    user_role = current_user.get("role", "staff")
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied. Required role: {', '.join(allowed_roles)}. Your role: {user_role}"
        )


# ============================================================
# AUDIT LOG HELPER (BackgroundTask-safe)
# ============================================================
def log_action(user_id: int, organization_id: int, action: str, entity_type: str, entity_id: int = None, details: str = None):
    """
    Non-blocking audit log writer. Runs in background thread with its own DB session.
    Safe to call from BackgroundTasks — does not share request-scoped session.
    """
    db = SessionLocal()
    try:
        audit = models.AuditLog(
            user_id=user_id,
            organization_id=organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details
        )
        db.add(audit)
        db.commit()
        logger.info("AUDIT: user=%s action=%s entity=%s:%s", user_id, action, entity_type, entity_id)
    except Exception as e:
        logger.error("AUDIT LOG FAILED: %s", str(e), exc_info=True)
        db.rollback()
    finally:
        db.close()


# ============================================================
# SOFT-DELETE GUARD
# ============================================================
def _check_product_not_deleted(db: Session, product_id: int, current_user: dict):
    """Verify a product exists and is not soft-deleted. Returns the product or raises 400."""
    product = org_filter(
        db.query(models.Product).filter(models.Product.id == product_id),
        models.Product,
        current_user,
        include_deleted=True
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.is_deleted:
        raise HTTPException(status_code=400, detail="Cannot operate on deleted product")
    return product


# ============================================================
# 🔴 PLAN LIMITS CONFIG (Task 3)
# ============================================================
PLAN_LIMITS = {
    "free": {
        "max_products": 10,
        "max_users": 2,
    },
    "pro": {
        "max_products": None,  # unlimited
        "max_users": None,     # unlimited
    }
}


def _get_subscription(db: Session, org_id: int) -> models.Subscription:
    """Fetch subscription for an org. Returns None if not found."""
    return db.query(models.Subscription).filter(
        models.Subscription.organization_id == org_id
    ).first()


def check_subscription_active(db: Session, org_id: int):
    """
    Verify the org has an active subscription.
    Free plan is always active. Pro plan checks expiry.
    Raises 403 if expired. Auto-marks expired subscriptions and logs the event.
    """
    sub = _get_subscription(db, org_id)
    if not sub:
        # No subscription record = free plan, always active
        return "free"
    
    if sub.plan == "free":
        return "free"
    
    # For paid plans, check status and expiry
    if sub.status != "active":
        raise HTTPException(status_code=403, detail="Subscription expired. Please renew to continue.")
    
    if sub.expiry_date and sub.expiry_date < datetime.utcnow():
        sub.status = "expired"
        db.commit()
        # Audit: auto-expiry event (fire-and-forget, own session)
        logger.warning("Subscription auto-expired for org=%s plan=%s", org_id, sub.plan)
        try:
            log_action(0, org_id, "SUBSCRIPTION_EXPIRED", "subscription", sub.id,
                       f"Plan '{sub.plan}' auto-expired at {sub.expiry_date.isoformat()}")
        except Exception:
            pass  # log_action already handles its own errors
        raise HTTPException(status_code=403, detail="Subscription expired. Please renew to continue.")
    
    return sub.plan


def require_active_subscription(db: Session, org_id: int) -> str:
    """
    Gate for ALL write operations. Checks subscription is active
    and returns the current plan name.
    Raises 403 if subscription is expired or inactive.
    """
    return check_subscription_active(db, org_id)


def check_plan_limit(db: Session, org_id: int, resource: str):
    """
    Check if the org has exceeded its plan limit for a resource.
    resource: 'products' or 'users'
    Raises 403 with upgrade message if limit exceeded.
    """
    sub = _get_subscription(db, org_id)
    plan = sub.plan if sub else "free"
    
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    max_val = limits.get(f"max_{resource}")
    
    if max_val is None:
        return  # unlimited
    
    # Count current usage
    if resource == "products":
        current = db.query(models.Product).filter(
            models.Product.shop_id == org_id,
            models.Product.is_deleted == False
        ).count()
    elif resource == "users":
        current = db.query(models.User).filter(
            models.User.organization_id == org_id,
            models.User.is_deleted == False
        ).count()
    else:
        return
    
    if current >= max_val:
        raise HTTPException(
            status_code=403,
            detail=f"Plan limit reached: {resource} ({current}/{max_val}). Upgrade to Pro for unlimited access."
        )


# ============================================================
# AUTH ENDPOINTS
# ============================================================
@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, background_tasks: BackgroundTasks, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    try:
        logger.info("LOGIN_ATTEMPT: email=%s", form_data.username)
        user = db.query(models.User).filter(
            (models.User.email == form_data.username) | 
            (models.User.username == form_data.username)
        ).first()
        
        if not user:
            logger.warning("USER_FOUND: False (email=%s)", form_data.username)
            raise HTTPException(status_code=401, detail="Incorrect credentials")

        logger.info("USER_FOUND: True (id=%s, org=%s)", user.id, user.organization_id)

        if getattr(user, 'is_deleted', False):
            logger.warning("USER_DELETED: True (id=%s)", user.id)
            raise HTTPException(status_code=401, detail="Account has been deactivated")
        
        if not user.hashed_password:
            logger.warning("LOGIN: OAuth-only user tried password login (id=%s)", user.id)
            raise HTTPException(status_code=401, detail="This account uses Google login. Please sign in with Google.")
        
        password_match = pwd_context.verify(form_data.password, user.hashed_password)
        logger.info("PASSWORD_MATCH: %s", password_match)
        
        if not password_match:
            raise HTTPException(status_code=401, detail="Incorrect credentials")
        
        # Generate access token (15 min) — include org_id + token_version
        tv = getattr(user, 'token_version', 0) or 0
        token_data = {
            "sub": user.email,
            "user_id": user.id,
            "organization_id": user.organization_id,
            "token_version": tv
        }
        access_token = create_access_token(data=token_data)
        
        # Generate refresh token (7 days)
        refresh_token = create_refresh_token(data=token_data)
        
        # Store hashed refresh token in DB
        user.hashed_refresh_token = pwd_context.hash(refresh_token)
        db.commit()
        
        logger.info("TOKEN_CREATED: True (user=%s)", user.email)
        
        # Audit: login event (background)
        background_tasks.add_task(
            log_action, user.id, user.organization_id or 0,
            "LOGIN", "user", user.id
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("LOGIN_ERROR: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/refresh")
@limiter.limit("30/minute")
def refresh_access_token(request: Request, body: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Accept a refresh token, validate, ROTATE both tokens, return new pair."""
    payload = decode_token(body.refresh_token)
    
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    
    user_id = payload.get("user_id")
    email = payload.get("sub")
    
    if not user_id or not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if getattr(user, 'is_deleted', False):
        raise HTTPException(status_code=401, detail="Account has been deactivated")
    
    if not user.hashed_refresh_token:
        raise HTTPException(status_code=401, detail="No active session. Please login again.")
    
    if not pwd_context.verify(body.refresh_token, user.hashed_refresh_token):
        raise HTTPException(status_code=401, detail="Refresh token revoked. Please login again.")
    
    # 🔴 ROTATION: Increment token_version to invalidate ALL old tokens
    user.token_version = (getattr(user, 'token_version', 0) or 0) + 1
    
    token_data = {"sub": email, "user_id": user.id, "token_version": user.token_version}
    new_access_token = create_access_token(data=token_data)
    new_refresh_token = create_refresh_token(data=token_data)
    
    # Store new hashed refresh token — old one is now invalid
    user.hashed_refresh_token = pwd_context.hash(new_refresh_token)
    db.commit()
    
    logger.info("Token rotation complete for user: %s (v=%s)", email, user.token_version)
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }


@router.post("/logout")
def logout(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Invalidate the refresh token and increment token_version to kill all sessions."""
    user = db.query(models.User).filter(models.User.id == current_user["user_id"]).first()
    if user:
        user.hashed_refresh_token = None
        user.token_version = (getattr(user, 'token_version', 0) or 0) + 1
        db.commit()
        logger.info("User logged out: %s (token_version=%s)", current_user["email"], user.token_version)
    
    background_tasks.add_task(
        log_action, current_user["user_id"], _org_id(current_user),
        "LOGOUT", "user", current_user["user_id"]
    )
    return {"message": "Logged out successfully"}


@router.get("/me")
@limiter.limit("100/minute")
def validate_token(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    
    # Fetch full user for extended fields
    user_id = current_user.get("user_id")
    db_user = db.query(models.User).filter(models.User.id == user_id).first() if user_id else None
    
    user_data = dict(current_user)
    if db_user:
        user_data["business_type"] = db_user.business_type or "customer"
        user_data["kyc_complete"] = db_user.kyc_complete or False
        user_data["full_name"] = db_user.full_name
    
    return {
        "status": "ok", 
        "user": user_data,
        "organization": {
            "id": org.id,
            "name": org.name,
            "ai_decision_mode": org.ai_decision_mode,
            "is_public": org.is_public,
        } if org else None
    }


# ============================================================
# INVITE (with audit)
# ============================================================
@router.post("/invite")
@limiter.limit("10/minute")
def invite_user(request: Request, background_tasks: BackgroundTasks, body: InviteRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    require_role(current_user, ["admin"])
    org_id = _org_id(current_user)

    # 🔴 SaaS: Check Subscription Status
    check_subscription_active(db, org_id)
    # 🔴 SaaS: Check Plan Limits
    check_plan_limit(db, org_id, "users")

    existing = db.query(models.User).filter(models.User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    if body.role not in ["admin", "staff"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'staff'")

    temp_password = pwd_context.hash("changeme123")
    new_user = models.User(
        email=body.email,
        hashed_password=temp_password,
        organization_id=org_id,
        role=body.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Audit: invite (background)
    background_tasks.add_task(
        log_action, current_user["user_id"], org_id,
        "INVITE", "user", new_user.id, f"Invited {body.email} as {body.role}"
    )

    return {
        "message": f"User {body.email} invited successfully",
        "user_id": new_user.id,
        "role": new_user.role,
        "organization_id": org_id,
        "note": "Temporary password set. Email invite flow not yet implemented."
    }


# ============================================================
# PRODUCTS CRUD
# ============================================================
@router.post("/products/", response_model=schemas.ProductResponse)
@limiter.limit("100/minute")
def create_product(request: Request, background_tasks: BackgroundTasks, product: schemas.ProductCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    # 🔴 SaaS: Check Subscription Status
    check_subscription_active(db, org_id)
    # 🔴 SaaS: Check Plan Limits
    check_plan_limit(db, org_id, "products")
    
    # SKU uniqueness check (org-scoped, excludes deleted)
    sku_query = org_filter(
        db.query(models.Product).filter(models.Product.sku == product.sku),
        models.Product,
        current_user
    )
    if sku_query.first():
        raise HTTPException(status_code=400, detail="Product with this SKU already exists")
    
    try:
        new_product = models.Product(**product.model_dump())
        new_product.shop_id = org_id
        db.add(new_product)
        db.flush()
        
        db_inv = models.Inventory(shop_id=org_id, product_id=new_product.id, quantity_on_hand=0)
        db.add(db_inv)
        
        db.commit()
        db.refresh(new_product)
        
        # Audit (background)
        background_tasks.add_task(
            log_action, current_user["user_id"], org_id,
            "CREATE", "product", new_product.id, f"SKU={product.sku}"
        )
        
        return new_product
    except Exception as e:
        db.rollback()
        logger.error("DB ERROR: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/products/", response_model=List[schemas.ProductResponse])
@limiter.limit("100/minute")
def read_products(request: Request, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    products = org_filter(db.query(models.Product), models.Product, current_user).offset(skip).limit(limit).all()
    return products


# ============================================================
# SALES
# ============================================================
@router.post("/sales/")
def record_sale(payload: schemas.SalesCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        org_id = _org_id(current_user)

        # 🔴 SaaS: Subscription gate
        require_active_subscription(db, org_id)

        # 🔴 Guard: prevent sale on deleted product
        _check_product_not_deleted(db, payload.product_id, current_user)

        inventory = org_filter(
            db.query(models.Inventory).filter(models.Inventory.product_id == payload.product_id),
            models.Inventory,
            current_user
        ).with_for_update().first()

        if not inventory:
            raise HTTPException(status_code=404, detail="Inventory not found")

        if inventory.quantity_on_hand < payload.quantity_sold:
            raise HTTPException(status_code=400, detail="Not enough stock")

        inventory.quantity_on_hand -= payload.quantity_sold
        inventory.updated_at = datetime.utcnow()

        # Sync product.updated_at so public API last_updated_at stays fresh
        product = db.query(models.Product).filter(models.Product.id == payload.product_id).first()
        if product:
            product.updated_at = datetime.utcnow()

        sale = models.Sale(
            product_id=payload.product_id,
            shop_id=org_id,
            quantity_sold=payload.quantity_sold
        )

        db.add(sale)
        db.commit()
        db.refresh(inventory)

        # Invalidate public API cache
        on_inventory_change()

        # 🔴 PART 2: Real-time trigger (ONLY low stock)
        # Prevent duplicate notifications (e.g. within 24 hours)
        if inventory.quantity_on_hand <= inventory.reorder_point:
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            recent_notif = db.query(models.Notification).filter(
                models.Notification.organization_id == org_id,
                models.Notification.type == "low_stock",
                models.Notification.message.like(f"%Product {payload.product_id}%"),
                models.Notification.created_at >= cutoff_time
            ).first()
            
            if not recent_notif:
                notif = models.Notification(
                    organization_id=org_id,
                    type="low_stock",
                    priority="high",
                    message=f"Low stock alert for Product {payload.product_id}: Only {inventory.quantity_on_hand} left."
                )
                db.add(notif)
                db.commit()

        # Audit (background)
        background_tasks.add_task(
            log_action, current_user["user_id"], org_id,
            "CREATE", "sale", sale.id, f"product={payload.product_id} qty={payload.quantity_sold}"
        )

        return {
            "message": "Sale recorded!",
            "stock_left": inventory.quantity_on_hand
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sales/history/{product_id}")
def get_sales_history(product_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    cutoff = datetime.utcnow() - timedelta(days=7)
    
    sales = org_filter(
        db.query(models.Sale).filter(
            models.Sale.product_id == product_id,
            models.Sale.sale_date >= cutoff
        ),
        models.Sale,
        current_user
    ).all()

    daily = {}
    for s in sales:
        date = s.sale_date.strftime("%Y-%m-%d")
        daily[date] = daily.get(date, 0) + s.quantity_sold

    return daily


# ============================================================
# INVENTORY
# ============================================================
@router.post("/inventory/add-stock")
def add_stock(payload: schemas.AddStockRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    # 🔴 SaaS: Subscription gate
    require_active_subscription(db, org_id)
    
    # 🔴 Guard: prevent stock ops on deleted product
    _check_product_not_deleted(db, payload.product_id, current_user)
    
    inventory = org_filter(
        db.query(models.Inventory).filter(models.Inventory.product_id == payload.product_id),
        models.Inventory,
        current_user
    ).first()

    if not inventory:
        inventory = models.Inventory(
            product_id=payload.product_id,
            shop_id=org_id,
            quantity_on_hand=payload.quantity
        )
        db.add(inventory)
    else:
        inventory.quantity_on_hand += payload.quantity
        inventory.updated_at = datetime.utcnow()

    # Sync product.updated_at so public API last_updated_at stays fresh
    product = db.query(models.Product).filter(models.Product.id == payload.product_id).first()
    if product:
        product.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(inventory)

    # Invalidate public API cache
    on_inventory_change()
    
    # Audit (background)
    background_tasks.add_task(
        log_action, current_user["user_id"], org_id,
        "ADD_STOCK", "inventory", inventory.id, f"product={payload.product_id} qty={payload.quantity}"
    )
    
    return {"message": "Stock updated successfully", "quantity_on_hand": inventory.quantity_on_hand}

@router.get("/inventory/summary", response_model=List[schemas.InventorySummaryResponse])
@limiter.limit("50/minute")
def get_inventory_summary(request: Request, limit: int = 100, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    # Join excludes soft-deleted products
    joined_data = db.query(models.Product, models.Inventory).join(
        models.Inventory, models.Product.id == models.Inventory.product_id
    ).filter(
        models.Product.shop_id == org_id,
        models.Inventory.shop_id == org_id,
        models.Product.is_deleted == False
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
    inventory = org_filter(
        db.query(models.Inventory).filter(models.Inventory.product_id == product_id),
        models.Inventory,
        current_user
    ).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="Not found")
    return inventory


# ============================================================
# PRODUCT UPDATE & DELETE
# ============================================================
@router.put("/products/{product_id}")
def update_product(product_id: int, updated: schemas.ProductCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    # 🔴 SaaS: Subscription gate
    require_active_subscription(db, org_id)
    
    product = org_filter(
        db.query(models.Product).filter(models.Product.id == product_id),
        models.Product,
        current_user
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        for key, value in updated.model_dump(exclude_unset=True).items():
            setattr(product, key, value)
        product.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(product)
        
        # Audit (background)
        background_tasks.add_task(
            log_action, current_user["user_id"], _org_id(current_user),
            "UPDATE", "product", product_id
        )
        
        return product
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Product with this SKU already exists")

@router.delete("/products/{product_id}")
def delete_product(product_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # RBAC: Only admins can delete products
    require_role(current_user, ["admin"])
    org_id = _org_id(current_user)
    
    # 🔴 SaaS: Subscription gate
    require_active_subscription(db, org_id)
    
    product = org_filter(
        db.query(models.Product).filter(models.Product.id == product_id),
        models.Product,
        current_user
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # SOFT DELETE
    product.is_deleted = True
    product.updated_at = datetime.utcnow()
    db.commit()
    
    # Audit (background)
    background_tasks.add_task(
        log_action, current_user["user_id"], _org_id(current_user),
        "DELETE", "product", product_id
    )
    
    return {"message": "Product deleted"}


# ============================================================
# PREDICTIONS
# ============================================================
@router.get("/predictions/{product_id}")
@limiter.limit("20/minute")
def get_prediction_insights(request: Request, product_id: int, window_size_days: int = 14, debug: bool = False, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    if debug and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Debug mode requires admin privileges")
    
    # 🔴 SaaS: Subscription gate (predictions require active plan)
    require_active_subscription(db, org_id)
    
    # 🔴 Guard: prevent predictions on deleted product
    _check_product_not_deleted(db, product_id, current_user)
    try:
        result = get_product_prediction(db, org_id, product_id, window_size_days, debug)
        return result
    except Exception as e:
        logger.error("PREDICTION ERROR: %s", str(e))
        # Safe fallback instead of crashing
        return {
            "product_id": product_id,
            "predicted_daily_demand": 0,
            "demand_min": 0,
            "demand_max": 0,
            "confidence_score": 0,
            "stockout_risk": 0,
            "overstock_risk": 0,
            "insight": "Not enough data yet. Add more sales to get AI predictions.",
            "recommended_action": "Record sales data to enable AI predictions.",
            "is_fallback": True
        }

@router.get("/ai/performance", response_model=schemas.AIPerformanceResponse)
def get_ai_performance(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    adjustments = db.query(models.OrderAdjustment).filter(
        models.OrderAdjustment.organization_id == org_id
    ).all()
    
    def calc_metrics(data):
        if not data:
            return {"avg_error_percentage": 0.0, "over_order_rate": 0.0, "under_order_rate": 0.0}
            
        total_error_pct = 0.0
        over_count = 0
        under_count = 0
        
        for adj in data:
            actual = adj.actual_qty
            suggested = adj.suggested_qty
            
            if actual > 0:
                total_error_pct += abs(suggested - actual) / actual
            elif suggested > 0:
                total_error_pct += 1.0 # 100% error if actual is 0 but suggested > 0
                
            if actual > suggested:
                over_count += 1
            elif actual < suggested:
                under_count += 1
                
        n = len(data)
        return {
            "avg_error_percentage": round((total_error_pct / n) * 100, 2),
            "over_order_rate": round((over_count / n) * 100, 2),
            "under_order_rate": round((under_count / n) * 100, 2)
        }
        
    cutoff_30d = datetime.utcnow() - timedelta(days=30)
    recent_adj = [a for a in adjustments if a.created_at >= cutoff_30d]
    
    return {
        "last_30_days": calc_metrics(recent_adj),
        "all_time": calc_metrics(adjustments)
    }

@router.patch("/settings/ai-mode", response_model=schemas.OrganizationResponse)
def update_ai_decision_mode(request: Request, payload: schemas.OrganizationModeUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can change the AI decision mode.")
        
    org_id = _org_id(current_user)
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    
    if payload.ai_decision_mode not in ["conservative", "balanced", "aggressive"]:
        raise HTTPException(status_code=400, detail="Invalid ai_decision_mode. Use conservative, balanced, or aggressive.")
        
    org.ai_decision_mode = payload.ai_decision_mode
    db.commit()
    db.refresh(org)
    
    return org


# ============================================================
# STORE VISIBILITY CONTROL
# ============================================================
@router.patch("/organization/visibility")
@limiter.limit("10/minute")
def update_store_visibility(request: Request, body: dict, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Toggle organization public visibility for marketplace."""
    require_role(current_user, ["admin"])
    org_id = _org_id(current_user)
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    is_public = body.get("is_public")
    if is_public is None or not isinstance(is_public, bool):
        raise HTTPException(status_code=400, detail="is_public must be true or false")
    
    org.is_public = is_public
    
    # Optional: update org details if provided
    if body.get("category"):
        org.category = body["category"]
    if body.get("address"):
        org.address = body["address"]
    if body.get("phone"):
        org.phone = body["phone"]
    
    db.commit()
    return {
        "message": f"Store visibility {'enabled' if is_public else 'disabled'}",
        "is_public": org.is_public,
    }

# ============================================================
# AUDIT LOGS (paginated, admin-only)
# ============================================================
@router.get("/audit-logs")
@limiter.limit("30/minute")
def get_audit_logs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    action: str = None,
    entity_type: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Paginated audit log viewer. Admin-only.
    Scoped to the caller's organization.
    """
    require_role(current_user, ["admin"])
    org_id = _org_id(current_user)
    
    # Cap limit to prevent abuse
    limit = min(limit, 200)
    
    query = db.query(models.AuditLog).filter(
        models.AuditLog.organization_id == org_id
    )
    
    # Optional filters
    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    
    total = query.count()
    
    logs = query.order_by(
        models.AuditLog.created_at.desc()
    ).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    }
# ============================================================
# 🔴 BILLING SYSTEM (Stripe Integrated)
# ============================================================

class BillingUpgradeRequest(BaseModel):
    plan: str  # "pro"


@router.post("/billing/create-checkout-session")
@limiter.limit("5/minute")
def create_checkout_session(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Create a Stripe Checkout Session for Pro plan.
    Returns checkout URL for frontend redirect.
    Requires Stripe environment variables to be configured.
    """
    from services.stripe_service import is_stripe_configured, get_or_create_customer, create_checkout_session as stripe_create_session

    require_role(current_user, ["admin"])
    org_id = _org_id(current_user)

    if not is_stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured. Set STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, and STRIPE_PRICE_ID_PRO."
        )

    sub = _get_subscription(db, org_id)
    if sub and sub.plan == "pro" and sub.status == "active":
        raise HTTPException(status_code=400, detail="Already on Pro plan with active subscription.")

    # Get or create Stripe customer
    existing_cid = sub.stripe_customer_id if sub else None
    customer_id = get_or_create_customer(
        email=current_user["email"],
        org_id=org_id,
        existing_customer_id=existing_cid
    )

    # Persist customer_id to both Subscription and Organization
    if not sub:
        sub = models.Subscription(organization_id=org_id)
        db.add(sub)
    sub.stripe_customer_id = customer_id

    # Also store on Organization for direct lookup
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if org:
        org.stripe_customer_id = customer_id

    db.commit()

    # Create checkout session
    session_data = stripe_create_session(customer_id, org_id)

    # Store pending payment record
    payment = models.Payment(
        organization_id=org_id,
        stripe_checkout_session_id=session_data["session_id"],
        status="pending",
        plan="pro"
    )
    db.add(payment)
    db.commit()

    background_tasks.add_task(
        log_action, current_user["user_id"], org_id,
        "CHECKOUT_CREATED", "subscription", sub.id, f"Stripe session: {session_data['session_id']}"
    )

    return {
        "checkout_url": session_data["checkout_url"],
        "session_id": session_data["session_id"]
    }


@router.post("/billing/upgrade")
@limiter.limit("5/minute")
def upgrade_plan(request: Request, body: BillingUpgradeRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Upgrade to Pro plan.
    If Stripe is configured, redirects to create-checkout-session flow.
    Otherwise, applies simulated upgrade (for dev/testing).
    """
    from services.stripe_service import is_stripe_configured

    require_role(current_user, ["admin"])
    org_id = _org_id(current_user)

    if body.plan != "pro":
        raise HTTPException(status_code=400, detail="Invalid plan selected")

    # If Stripe is configured, direct users to the checkout flow
    if is_stripe_configured():
        return {
            "message": "Stripe is configured. Use POST /billing/create-checkout-session instead.",
            "redirect": "/api/v1/billing/create-checkout-session"
        }

    # Simulated upgrade fallback (dev/testing only)
    sub = _get_subscription(db, org_id)
    if not sub:
        sub = models.Subscription(organization_id=org_id)
        db.add(sub)

    sub.plan = "pro"
    sub.status = "active"
    sub.expiry_date = datetime.utcnow() + timedelta(days=30)
    db.commit()

    background_tasks.add_task(
        log_action, current_user["user_id"], org_id,
        "UPGRADE", "subscription", sub.id, f"Simulated upgrade to {body.plan}"
    )

    return {"message": "Successfully upgraded to Pro plan!", "plan": "pro", "expiry": sub.expiry_date}


@router.post("/billing/downgrade")
@limiter.limit("5/minute")
def downgrade_plan(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Downgrade to free plan. Existing resources are preserved (read/update/delete allowed),
    but new resource creation is blocked once free-plan limits are exceeded.
    If Stripe is active, cancels the Stripe subscription.
    """
    from services.stripe_service import is_stripe_configured

    require_role(current_user, ["admin"])
    org_id = _org_id(current_user)

    sub = _get_subscription(db, org_id)
    if not sub or sub.plan == "free":
        raise HTTPException(status_code=400, detail="Already on the free plan.")

    old_plan = sub.plan

    # If Stripe is configured and there's an active Stripe subscription, cancel it
    if is_stripe_configured() and sub.stripe_subscription_id:
        import stripe as stripe_lib
        try:
            stripe_lib.Subscription.cancel(sub.stripe_subscription_id)
            logger.info("Cancelled Stripe subscription %s for org=%s", sub.stripe_subscription_id, org_id)
        except Exception as e:
            logger.error("Failed to cancel Stripe subscription %s: %s", sub.stripe_subscription_id, str(e))
            # Continue with local downgrade even if Stripe cancel fails

    sub.plan = "free"
    sub.status = "active"
    sub.expiry_date = None
    sub.stripe_subscription_id = None  # Clear Stripe sub reference
    db.commit()

    # Check if existing resources exceed free limits (warn but don't delete)
    product_count = db.query(models.Product).filter(
        models.Product.shop_id == org_id,
        models.Product.is_deleted == False
    ).count()
    user_count = db.query(models.User).filter(
        models.User.organization_id == org_id,
        models.User.is_deleted == False
    ).count()

    free_limits = PLAN_LIMITS["free"]
    warnings = []
    if free_limits["max_products"] and product_count > free_limits["max_products"]:
        warnings.append(f"Products: {product_count}/{free_limits['max_products']} (new creation blocked until under limit)")
    if free_limits["max_users"] and user_count > free_limits["max_users"]:
        warnings.append(f"Users: {user_count}/{free_limits['max_users']} (new invites blocked until under limit)")

    background_tasks.add_task(
        log_action, current_user["user_id"], org_id,
        "DOWNGRADE", "subscription", sub.id, f"Downgraded from {old_plan} to free"
    )

    result = {
        "message": f"Downgraded from {old_plan} to free plan.",
        "plan": "free",
        "note": "Existing resources are preserved. New creation is blocked if limits are exceeded."
    }
    if warnings:
        result["warnings"] = warnings

    return result


@router.post("/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe Webhook handler with signature verification and idempotency.
    Deduplicates events via stripe_events table.
    Processes: checkout.session.completed, invoice.payment_succeeded,
    invoice.payment_failed, customer.subscription.updated/created/deleted.
    Falls back to stub response if Stripe is not configured.
    """
    from services.stripe_service import is_stripe_configured, verify_webhook_signature, extract_subscription_data

    if not is_stripe_configured():
        return {"status": "webhook_received", "note": "Stripe not configured, ignoring"}

    # Read raw body for signature verification
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")

    try:
        event = verify_webhook_signature(payload, sig_header)
    except ValueError as e:
        logger.error("Webhook signature verification failed: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))

    event_id = event.get("id")
    event_type = event["type"]
    logger.info("Stripe webhook received: %s (id=%s)", event_type, event_id)

    # ── IDEMPOTENCY CHECK ──
    if event_id:
        existing_event = db.query(models.StripeEvent).filter(
            models.StripeEvent.event_id == event_id
        ).first()
        if existing_event:
            logger.info("Duplicate Stripe event %s, skipping", event_id)
            return {"status": "duplicate", "event_id": event_id}

    # Extract normalized data from event
    event_data = extract_subscription_data(event)
    org_id_str = event_data.get("org_id")

    # ── MULTI-LAYER ORG RESOLUTION ──
    # Layer 1: metadata.org_id from Stripe event
    org_id = None
    if org_id_str:
        try:
            org_id = int(org_id_str)
            # Validate org actually exists
            org_exists = db.query(models.Organization).filter(
                models.Organization.id == org_id
            ).first()
            if not org_exists:
                logger.warning("Webhook org_id=%s from metadata does not exist in DB", org_id)
                org_id = None
        except (ValueError, TypeError):
            pass

    # Layer 2: Look up by stripe_customer_id in Subscription table
    if not org_id and event_data.get("stripe_customer_id"):
        sub_lookup = db.query(models.Subscription).filter(
            models.Subscription.stripe_customer_id == event_data["stripe_customer_id"]
        ).first()
        if sub_lookup:
            org_id = sub_lookup.organization_id

    # Layer 3: Look up by stripe_customer_id in Organization table
    if not org_id and event_data.get("stripe_customer_id"):
        org_lookup = db.query(models.Organization).filter(
            models.Organization.stripe_customer_id == event_data["stripe_customer_id"]
        ).first()
        if org_lookup:
            org_id = org_lookup.id

    if not org_id:
        logger.warning("Webhook event %s (id=%s): could not resolve org_id, skipping", event_type, event_id)
        # Still record the event for audit trail
        if event_id:
            db.add(models.StripeEvent(
                event_id=event_id, event_type=event_type,
                status="skipped", details="org_id not resolvable"
            ))
            db.commit()
        return {"status": "skipped", "reason": "org_id not resolvable"}

    # ── FILTER HANDLED EVENTS ──
    HANDLED_EVENTS = {
        "checkout.session.completed",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
        "customer.subscription.updated",
        "customer.subscription.created",
        "customer.subscription.deleted",
    }

    if event_type not in HANDLED_EVENTS:
        logger.info("Webhook event %s not handled, acknowledging", event_type)
        if event_id:
            db.add(models.StripeEvent(
                event_id=event_id, event_type=event_type,
                organization_id=org_id, status="acknowledged"
            ))
            db.commit()
        return {"status": "acknowledged", "event": event_type}

    # ── UPDATE SUBSCRIPTION ──
    sub = _get_subscription(db, org_id)
    if not sub:
        sub = models.Subscription(organization_id=org_id)
        db.add(sub)

    if event_data["stripe_customer_id"]:
        sub.stripe_customer_id = event_data["stripe_customer_id"]
        # Sync to Organization model
        org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
        if org and not org.stripe_customer_id:
            org.stripe_customer_id = event_data["stripe_customer_id"]

    if event_data["stripe_subscription_id"]:
        sub.stripe_subscription_id = event_data["stripe_subscription_id"]

    plan_status = event_data.get("plan_status")

    if plan_status == "active":
        sub.plan = "pro"
        sub.status = "active"
        if event_data.get("expiry_date"):
            sub.expiry_date = event_data["expiry_date"]
        elif not sub.expiry_date:
            sub.expiry_date = datetime.utcnow() + timedelta(days=30)

    elif plan_status == "expired":
        # Handle cancellation vs payment failure
        if event_type == "customer.subscription.deleted":
            # Full cancellation: downgrade to free, clear Stripe ref
            sub.plan = "free"
            sub.status = "active"
            sub.expiry_date = None
            sub.stripe_subscription_id = None
            logger.info("Subscription cancelled via Stripe for org=%s, downgraded to free", org_id)
        else:
            # Payment failure or other expiry: mark expired, keep plan for grace period
            sub.status = "expired"
            logger.info("Subscription expired for org=%s via %s", org_id, event_type)

    # ── STORE PAYMENT METADATA ──
    if event_data.get("payment_intent_id"):
        existing_payment = db.query(models.Payment).filter(
            models.Payment.stripe_payment_intent_id == event_data["payment_intent_id"]
        ).first()

        if not existing_payment:
            payment = models.Payment(
                organization_id=org_id,
                stripe_payment_intent_id=event_data["payment_intent_id"],
                amount=event_data.get("amount"),
                currency=event_data.get("currency"),
                status="succeeded" if plan_status == "active" else "failed",
                plan="pro",
                metadata_json=json.dumps({
                    "event_type": event_type,
                    "event_id": event_id,
                    "stripe_subscription_id": event_data.get("stripe_subscription_id"),
                })
            )
            db.add(payment)
        else:
            existing_payment.status = "succeeded" if plan_status == "active" else "failed"
            existing_payment.updated_at = datetime.utcnow()

    # Update checkout session payment record if this is a checkout completion
    if event_type == "checkout.session.completed":
        checkout_session_id = event["data"]["object"].get("id")
        if checkout_session_id:
            pending_payment = db.query(models.Payment).filter(
                models.Payment.stripe_checkout_session_id == checkout_session_id,
                models.Payment.status == "pending"
            ).first()
            if pending_payment:
                pending_payment.status = "succeeded"
                pending_payment.stripe_payment_intent_id = event_data.get("payment_intent_id")
                pending_payment.amount = event_data.get("amount")
                pending_payment.currency = event_data.get("currency")
                pending_payment.updated_at = datetime.utcnow()

    # ── RECORD IDEMPOTENCY EVENT ──
    if event_id:
        db.add(models.StripeEvent(
            event_id=event_id,
            event_type=event_type,
            organization_id=org_id,
            status="processed",
            details=f"plan_status={plan_status}, amount={event_data.get('amount')}"
        ))

    db.commit()

    # ── AUDIT LOG ──
    audit_action = {
        "checkout.session.completed": "STRIPE_CHECKOUT_COMPLETED",
        "invoice.payment_succeeded": "STRIPE_PAYMENT_SUCCEEDED",
        "invoice.payment_failed": "STRIPE_PAYMENT_FAILED",
        "customer.subscription.updated": "STRIPE_SUBSCRIPTION_UPDATED",
        "customer.subscription.created": "STRIPE_SUBSCRIPTION_CREATED",
        "customer.subscription.deleted": "STRIPE_SUBSCRIPTION_CANCELLED",
    }.get(event_type, f"STRIPE_{event_type.upper()}")

    try:
        log_action(
            0, org_id, audit_action, "subscription",
            sub.id if sub.id else None,
            f"Stripe event: {event_type} (id={event_id}), status={plan_status}, amount={event_data.get('amount')}"
        )
    except Exception:
        pass  # log_action handles its own errors

    logger.info("Webhook processed: %s (id=%s) for org=%s status=%s", event_type, event_id, org_id, plan_status)
    return {"status": "processed", "event": event_type, "event_id": event_id}


@router.get("/billing/status")
def get_billing_status(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Return current plan name, limits, and current usage counts."""
    org_id = _org_id(current_user)
    sub = _get_subscription(db, org_id)
    plan = sub.plan if sub else "free"
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    # Current usage for limit-aware resources
    product_count = db.query(models.Product).filter(
        models.Product.shop_id == org_id,
        models.Product.is_deleted == False
    ).count()
    user_count = db.query(models.User).filter(
        models.User.organization_id == org_id,
        models.User.is_deleted == False
    ).count()

    return {
        "plan": plan,
        "status": sub.status if sub else "active",
        "limits": limits,
        "usage": {
            "products": product_count,
            "users": user_count
        },
        "expiry": sub.expiry_date.isoformat() if sub and sub.expiry_date else None
    }

# ============================================================
# NOTIFICATIONS
# ============================================================
@router.get("/notifications", response_model=List[schemas.NotificationResponse])
def get_notifications(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    return db.query(models.Notification).filter(
        models.Notification.organization_id == org_id
    ).order_by(models.Notification.created_at.desc()).limit(50).all()

@router.patch("/notifications/{notif_id}/read", response_model=schemas.NotificationResponse)
def mark_notification_read(notif_id: int, payload: schemas.NotificationUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    notif = db.query(models.Notification).filter(
        models.Notification.id == notif_id,
        models.Notification.organization_id == org_id
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = payload.is_read
    db.commit()
    db.refresh(notif)
    return notif

@router.patch("/notifications/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    db.query(models.Notification).filter(
        models.Notification.organization_id == org_id,
        models.Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read"}

# ============================================================
# PLATFORM ADMIN ENDPOINTS
# ============================================================
@router.get("/admin/stats")
def get_admin_stats(db: Session = Depends(get_db), current_admin: dict = Depends(require_platform_admin)):
    """
    Returns global platform statistics for the platform administrator.
    Bypasses tenant isolation by completely omitting organization_id filters.
    """
    try:
        total_users = db.query(models.User).filter(models.User.is_deleted == False).count()
        total_organizations = db.query(models.Organization).count()
        total_products = db.query(models.Product).filter(models.Product.is_deleted == False).count()
        
        # Active users last 7 days based on updated_at (or could use audit logs)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        active_users_last_7_days = db.query(models.User).filter(
            models.User.is_deleted == False,
            models.User.updated_at >= seven_days_ago
        ).count()
        
        # Average AI Accuracy across the entire platform
        # Calculate from OrderAdjustment table
        adjustments = db.query(models.OrderAdjustment).all()
        avg_ai_accuracy = 0.0
        if adjustments:
            total_error = sum(adj.error_percentage for adj in adjustments)
            avg_error = total_error / len(adjustments)
            avg_ai_accuracy = max(0, 100 - avg_error)

        # Top 5 Organizations by number of sales
        from sqlalchemy import func
        top_orgs_query = db.query(
            models.Organization.id,
            models.Organization.name,
            func.count(models.Sale.id).label("sales_count")
        ).join(models.Sale, models.Sale.organization_id == models.Organization.id) \
         .group_by(models.Organization.id, models.Organization.name) \
         .order_by(func.count(models.Sale.id).desc()) \
         .limit(5).all()
         
        top_5_organizations = [
            {"id": row.id, "name": row.name, "metric": row.sales_count} for row in top_orgs_query
        ]
        
        # Low performing orgs (for simplicity, orgs with highest average error percentage)
        low_orgs_query = db.query(
            models.Organization.id,
            models.Organization.name,
            func.avg(models.OrderAdjustment.error_percentage).label("avg_error")
        ).join(models.OrderAdjustment, models.OrderAdjustment.organization_id == models.Organization.id) \
         .group_by(models.Organization.id, models.Organization.name) \
         .having(func.avg(models.OrderAdjustment.error_percentage) > 20) \
         .order_by(func.avg(models.OrderAdjustment.error_percentage).desc()) \
         .limit(5).all()

        low_performing_orgs = [
            {"id": row.id, "name": row.name, "metric": round(row.avg_error, 2)} for row in low_orgs_query
        ]

        return {
            "total_users": total_users,
            "total_organizations": total_organizations,
            "total_products": total_products,
            "active_users_last_7_days": active_users_last_7_days,
            "average_ai_accuracy": round(avg_ai_accuracy, 2),
            "top_5_organizations": top_5_organizations,
            "low_performing_orgs": low_performing_orgs
        }
    except Exception as e:
        logger.error(f"Failed to fetch admin stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch platform statistics")


# ============================================================
# ADMIN KYC ACCESS
# ============================================================
@router.get("/admin/kyc")
@limiter.limit("20/minute")
def admin_get_kyc(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Admin-only: view all KYC records."""
    require_role(current_user, ["admin"])
    
    kyc_records = db.query(models.UserKYC).order_by(models.UserKYC.created_at.desc()).all()
    return [
        {
            "id": k.id,
            "user_id": k.user_id,
            "full_name": k.full_name,
            "age": k.age,
            "phone": k.phone,
            "email": k.email,
            "address": k.address,
            "business_type": k.business_type,
            "created_at": k.created_at,
        }
        for k in kyc_records
    ]


@router.get("/me/kyc")
@limiter.limit("30/minute")
def get_my_kyc(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get own KYC data."""
    user_id = current_user.get("user_id")
    kyc = db.query(models.UserKYC).filter(models.UserKYC.user_id == user_id).first()
    if not kyc:
        return {"kyc": None}
    return {
        "kyc": {
            "full_name": kyc.full_name,
            "age": kyc.age,
            "phone": kyc.phone,
            "email": kyc.email,
            "address": kyc.address,
            "business_type": kyc.business_type,
        }
    }
