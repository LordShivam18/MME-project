from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

import models.core as models
import schemas.core as schemas
from database import get_db
from auth import get_current_user
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


# ============================================================
# ORDERS (Atomic creation)
# ============================================================

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

    # 1. Verify Contact Ownership
    contact = db.query(models.Contact).filter(
        models.Contact.id == payload.contact_id,
        models.Contact.organization_id == org_id,
        models.Contact.is_deleted == False
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found or does not belong to your organization")

    # 2. Setup Atomic Transaction Block
    total_amount = 0.0
    new_order = models.Order(
        organization_id=org_id,
        contact_id=payload.contact_id,
        status="pending"
    )
    db.add(new_order)
    db.flush() # Yields new_order.id

    # 3. Process Items and Compute Total strictly on Server
    for item in payload.items:
        # Verify Product Ownership
        product = db.query(models.Product).filter(
            models.Product.id == item.product_id,
            models.Product.shop_id == org_id,
            models.Product.is_deleted == False
        ).first()
        
        if not product:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Product ID {item.product_id} invalid or unauthorized")
        
        line_price = product.selling_price
        total_amount += (line_price * item.quantity)
        
        order_item = models.OrderItem(
            order_id=new_order.id,
            product_id=product.id,
            quantity=item.quantity,
            price_at_time=line_price
        )
        db.add(order_item)

    new_order.total_amount = total_amount
    db.commit()
    db.refresh(new_order)
    
    return new_order

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
        
    if payload.status is not None:
        order.status = payload.status
    if payload.delivery_status is not None:
        order.delivery_status = payload.delivery_status
    if payload.tracking_number is not None:
        order.tracking_number = payload.tracking_number
        
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order
