from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

import models.core as models
import schemas.core as schemas
from database import get_db
from auth import get_current_user, require_seller
from routers.endpoints import _org_id, org_filter, require_active_subscription
from limiter import limiter

router = APIRouter()

# ============================================================
# CONTACTS
# ============================================================

@router.get("/contacts", response_model=List[schemas.ContactResponse])
@limiter.limit("50/minute")
def get_contacts(request: Request, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    contacts = db.query(models.Contact).filter(
        models.Contact.organization_id == org_id,
        models.Contact.is_deleted == False
    ).offset(skip).limit(limit).all()
    return contacts

@router.post("/contacts", response_model=schemas.ContactResponse)
@limiter.limit("20/minute")
def create_contact(request: Request, payload: schemas.ContactCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    require_active_subscription(db, org_id)

    if payload.phone:
        existing = db.query(models.Contact).filter(
            models.Contact.organization_id == org_id,
            models.Contact.phone == payload.phone,
            models.Contact.is_deleted == False
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="A contact with this phone number already exists.")

    new_contact = models.Contact(
        **payload.model_dump(),
        organization_id=org_id
    )
    db.add(new_contact)
    db.commit()
    db.refresh(new_contact)
    return new_contact

@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.organization_id == org_id,
        models.Contact.is_deleted == False
    ).first()
    
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    contact.is_deleted = True
    db.commit()
    return {"message": "Contact deleted"}

# Simple TTL Cache for Stats (5 minutes)
import time
stats_cache = {}

@router.get("/contacts/{contact_id}/stats")
def get_contact_stats(contact_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    cache_key = f"{org_id}_{contact_id}"
    
    # Check cache (5 minutes = 300 seconds)
    if cache_key in stats_cache:
        data, timestamp = stats_cache[cache_key]
        if time.time() - timestamp < 300:
            return data

    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.organization_id == org_id
    ).first()
    
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Fetch last 50 orders
    recent_orders = db.query(models.Order).filter(
        models.Order.contact_id == contact_id,
        models.Order.is_deleted == False
    ).order_by(models.Order.created_at.desc()).limit(50).all()

    total_orders = len(recent_orders)
    last_order_date = recent_orders[0].created_at if total_orders > 0 else None

    # Compute avg_delivery_time by examining OrderStatusHistory
    delivery_times = []
    if total_orders > 0:
        order_ids = [o.id for o in recent_orders]
        histories = db.query(models.OrderStatusHistory).filter(
            models.OrderStatusHistory.order_id.in_(order_ids),
            models.OrderStatusHistory.to_status.in_(["shipped", "delivered"])
        ).order_by(models.OrderStatusHistory.changed_at.asc()).all()

        history_map = {}
        for h in histories:
            if h.order_id not in history_map:
                history_map[h.order_id] = {}
            if h.to_status == "shipped" and "shipped" not in history_map[h.order_id]:
                history_map[h.order_id]["shipped"] = h.changed_at
            if h.to_status == "delivered" and "delivered" not in history_map[h.order_id]:
                history_map[h.order_id]["delivered"] = h.changed_at

        for o_id, stamps in history_map.items():
            if "shipped" in stamps and "delivered" in stamps:
                delta = (stamps["delivered"] - stamps["shipped"]).total_seconds()
                if delta >= 0:
                    delivery_times.append(delta)

    avg_del = sum(delivery_times) / len(delivery_times) / 86400.0 if delivery_times else 0.0

    result = {
        "contact_id": contact_id,
        "total_orders_last_50": total_orders,
        "last_order_date": last_order_date,
        "avg_delivery_time_days": round(avg_del, 2)
    }
    
    stats_cache[cache_key] = (result, time.time())
    return result

# ============================================================
# ORDERS (Atomic creation)
# ============================================================

@router.get("/orders", response_model=List[schemas.OrderResponse])
def get_all_orders(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    orders = db.query(models.Order).filter(
        models.Order.organization_id == org_id,
        models.Order.is_deleted == False
    ).order_by(models.Order.created_at.desc()).all()
    return orders

@router.get("/contacts/{contact_id}/orders", response_model=List[schemas.OrderResponse])
@limiter.limit("50/minute")
def get_contact_orders(request: Request, contact_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    # Verify contact ownership
    contact = db.query(models.Contact).filter(
        models.Contact.id == contact_id,
        models.Contact.organization_id == org_id
    ).first()
    
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    orders = db.query(models.Order).filter(
        models.Order.contact_id == contact_id,
        models.Order.organization_id == org_id,
        models.Order.is_deleted == False
    ).order_by(models.Order.created_at.desc()).all()
    return orders

@router.post("/orders", response_model=schemas.OrderResponse)
@limiter.limit("20/minute")
def create_order(request: Request, payload: schemas.OrderCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    require_active_subscription(db, org_id)

    try:
        # 1. Verify Contact Ownership
        contact = db.query(models.Contact).filter(
            models.Contact.id == payload.contact_id,
            models.Contact.organization_id == org_id,
            models.Contact.is_deleted == False
        ).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found or does not belong to your organization")

        # Validate items
        if not payload.items or len(payload.items) == 0:
            raise HTTPException(status_code=400, detail="Order must contain at least one item")

        # 2. Setup Atomic Transaction Block
        total_amount = 0.0
        new_order = models.Order(
            organization_id=org_id,
            contact_id=payload.contact_id,
            status="pending"
        )
        db.add(new_order)
        db.flush() # Yields new_order.id

        history = models.OrderStatusHistory(
            order_id=new_order.id,
            from_status=None,
            to_status="pending",
            changed_by=current_user.get("email", "system")
        )
        db.add(history)

        # 3. Process Items and Compute Total strictly on Server
        for item in payload.items:
            if not item.product_id or item.quantity <= 0:
                db.rollback()
                raise HTTPException(status_code=400, detail=f"Invalid item: product_id={item.product_id}, quantity={item.quantity}")

            # Verify Product Ownership
            product = db.query(models.Product).filter(
                models.Product.id == item.product_id,
                models.Product.shop_id == org_id,
                models.Product.is_deleted == False
            ).first()
            
            if not product:
                db.rollback()
                logger.warning(f"Order: product {item.product_id} not found for org {org_id}")
                raise HTTPException(status_code=400, detail=f"Product ID {item.product_id} invalid or unauthorized")
            
            logger.info(f"Order item: product={product.name} (id={product.id}), qty={item.quantity}, price={product.selling_price}")

            line_price = product.selling_price or 0
            total_amount += (line_price * item.quantity)
            
            order_item = models.OrderItem(
                order_id=new_order.id,
                product_id=product.id,
                quantity=item.quantity,
                price_at_time=line_price
            )
            db.add(order_item)
            
            # AI Engine Auto-Capture: Order Adjustment
            try:
                insight = db.query(models.ProductInsight).filter(
                    models.ProductInsight.product_id == product.id,
                    models.ProductInsight.organization_id == org_id
                ).first()
                if insight:
                    from logic_engine import InventoryLogic
                    inv = db.query(models.Inventory).filter(
                        models.Inventory.product_id == product.id,
                        models.Inventory.shop_id == org_id
                    ).first()
                    if inv:
                        lead_time = product.lead_time_days or 7
                        suggested_qty = InventoryLogic.suggest_order_quantity(
                            current_inventory=inv.quantity_on_hand,
                            reorder_point=inv.reorder_point,
                            predicted_daily_demand=insight.predicted_daily_demand,
                            lead_time_days=lead_time
                        )
                        if suggested_qty > 0:
                            adj = models.OrderAdjustment(
                                organization_id=org_id,
                                product_id=product.id,
                                suggested_qty=suggested_qty,
                                actual_qty=item.quantity,
                                adjustment_reason="Auto-captured on order creation"
                            )
                            db.add(adj)
            except Exception as ai_err:
                logger.warning(f"Order: AI capture skipped for product {product.id}: {str(ai_err)}")

        new_order.total_amount = total_amount
        db.commit()
        db.refresh(new_order)
        
        logger.info(f"Order {new_order.id} created: {len(payload.items)} items, total={total_amount}")
        return new_order

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Order creation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create order. Please try again.")

@router.get("/orders/{order_id}", response_model=schemas.OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.organization_id == org_id,
        models.Order.is_deleted == False
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.patch("/orders/{order_id}/status", response_model=schemas.OrderResponse)
def update_order_status(order_id: int, payload: schemas.OrderUpdateStatus, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.organization_id == org_id,
        models.Order.is_deleted == False
    ).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    ALLOWED_TRANSITIONS = {
        "pending": ["confirmed", "cancelled"],
        "confirmed": ["packed", "shipped", "cancelled"],
        "packed": ["shipped", "cancelled"],
        "shipped": ["delivered", "returned"],
        "delivered": ["returned"],
        "returned": [],
        "cancelled": []
    }

    history_added = False
    if payload.status is not None and payload.status != order.status:
        if payload.status not in ALLOWED_TRANSITIONS.get(order.status, []):
            raise HTTPException(status_code=400, detail=f"Invalid transition from {order.status} to {payload.status}")
        
        history = models.OrderStatusHistory(
            order_id=order.id,
            from_status=order.status,
            to_status=payload.status,
            changed_by=current_user.get("email", "system")
        )
        db.add(history)
        order.status = payload.status
        history_added = True

    if payload.delivery_status is not None:
        order.delivery_status = payload.delivery_status
    if payload.tracking_number is not None:
        order.tracking_number = payload.tracking_number
        
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    
    # Notification trigger for order status changes
    if history_added:
        notif = models.Notification(
            organization_id=org_id,
            type="order_update",
            priority="high" if order.status in ["shipped", "delivered"] else "medium",
            message=f"Order #{order.id} status changed to {order.status}."
        )
        db.add(notif)
        db.commit()
    
    return order


# ============================================================
# ORDER TIMELINE
# ============================================================
@router.get("/orders/{order_id}/timeline")
def get_order_timeline(order_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get full status timeline for an order."""
    from sqlalchemy import or_
    org_id = _org_id(current_user)
    user_id = current_user.get("user_id")
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        or_(models.Order.organization_id == org_id, models.Order.user_id == user_id),
        models.Order.is_deleted == False
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    history = (
        db.query(models.OrderStatusHistory)
        .filter(models.OrderStatusHistory.order_id == order_id)
        .order_by(models.OrderStatusHistory.changed_at.asc())
        .all()
    )

    timeline = []
    # Add initial "placed" event from order creation
    timeline.append({"step": "placed", "time": order.created_at.isoformat() if order.created_at else None})
    
    for h in history:
        timeline.append({
            "step": h.to_status,
            "time": h.changed_at.isoformat() if h.changed_at else None,
        })

    return {
        "order_id": order.id,
        "status": order.status,
        "timeline": timeline,
    }
