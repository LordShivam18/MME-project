from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session, Query
from sqlalchemy.exc import IntegrityError
from typing import List
import logging
import os
from datetime import datetime, timedelta
from pydantic import BaseModel
from functools import wraps

from database import get_db, SessionLocal
from models import core as models
from schemas import core as schemas
from services.prediction_service import get_product_prediction, invalidate_prediction_cache
from limiter import limiter
from auth import get_current_user, pwd_context, create_access_token, create_refresh_token, decode_token
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
    Raises 403 if expired.
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
        raise HTTPException(status_code=403, detail="Subscription expired. Please renew to continue.")
    
    return sub.plan


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
    logger.info("User lookup executed")
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    if not user:
        logger.info("User not found")
        raise HTTPException(status_code=401, detail="Incorrect credentials")

    if getattr(user, 'is_deleted', False):
        logger.info("User account deactivated")
        raise HTTPException(status_code=401, detail="Account has been deactivated")
        
    logger.info("User found")
    
    if not pwd_context.verify(form_data.password, user.hashed_password):
        logger.warning("Password failed")
        raise HTTPException(status_code=401, detail="Incorrect credentials")
        
    logger.info("Password verified")
    
    # Generate access token (15 min) — include token_version for replay protection
    tv = getattr(user, 'token_version', 0) or 0
    token_data = {"sub": user.email, "user_id": user.id, "token_version": tv}
    access_token = create_access_token(data=token_data)
    
    # Generate refresh token (7 days)
    refresh_token = create_refresh_token(data=token_data)
    
    # Store hashed refresh token in DB
    user.hashed_refresh_token = pwd_context.hash(refresh_token)
    db.commit()
    
    logger.info("JWT access + refresh tokens generated")
    
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
def validate_token(request: Request, current_user: dict = Depends(get_current_user)):
    return {"status": "ok", "user": current_user}


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

        sale = models.Sale(
            product_id=payload.product_id,
            shop_id=org_id,
            quantity_sold=payload.quantity_sold
        )

        db.add(sale)
        db.commit()
        db.refresh(inventory)

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

    db.commit()
    db.refresh(inventory)
    
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
def get_prediction_insights(request: Request, product_id: int, window_size_days: int = 14, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # 🔴 Guard: prevent predictions on deleted product
    _check_product_not_deleted(db, product_id, current_user)
    
    org_id = _org_id(current_user)
    try:
        result = get_product_prediction(db, org_id, product_id, window_size_days)
        return result
    except Exception as e:
        logger.error("PREDICTION ERROR: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))


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
# 🔴 BILLING SYSTEM (Stripe/Razorpay Ready)
# ============================================================

class BillingUpgradeRequest(BaseModel):
    plan: str  # "pro"

@router.post("/billing/upgrade")
@limiter.limit("5/minute")
def upgrade_plan(request: Request, body: BillingUpgradeRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Simulated upgrade to Pro plan.
    In production, this would redirect to Stripe/Razorpay checkout.
    """
    require_role(current_user, ["admin"])
    org_id = _org_id(current_user)
    
    if body.plan != "pro":
        raise HTTPException(status_code=400, detail="Invalid plan selected")

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
        "UPGRADE", "subscription", sub.id, f"Upgraded to {body.plan}"
    )

    return {"message": "Successfully upgraded to Pro plan!", "plan": "pro", "expiry": sub.expiry_date}


@router.post("/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe/Razorpay Webhook listener stub.
    Security: Verify signature in production!
    """
    # Pseudo-logic for handling payment success
    # 1. Verify webhook signature
    # 2. Extract org_id and event type
    # 3. Update subscription status in DB
    return {"status": "webhook_received"}


@router.get("/billing/status")
def get_billing_status(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Return current plan name and limits."""
    org_id = _org_id(current_user)
    sub = _get_subscription(db, org_id)
    plan = sub.plan if sub else "free"
    
    return {
        "plan": plan,
        "status": sub.status if sub else "active",
        "limits": PLAN_LIMITS.get(plan),
        "expiry": sub.expiry_date if sub else None
    }
