from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from datetime import datetime

import models.core as models
from pydantic import BaseModel
from database import get_db
from auth import get_current_user
from routers.endpoints import _org_id

router = APIRouter()

# --- Schemas ---

class TicketCreate(BaseModel):
    order_id: int
    issue_type: str
    priority: str = "medium"

class TicketMessageCreate(BaseModel):
    message: str

class TicketStatusUpdate(BaseModel):
    status: str # open, in_progress, resolved

class TicketEventResponse(BaseModel):
    id: int
    old_status: str | None
    new_status: str
    changed_by: int
    created_at: datetime
    class Config: from_attributes = True

class TicketMessageResponse(BaseModel):
    id: int
    sender_id: int
    message: str
    created_at: datetime
    class Config: from_attributes = True

class TicketResponse(BaseModel):
    id: int
    user_id: int
    order_id: int
    organization_id: int
    issue_type: str
    status: str
    priority: str
    created_at: datetime
    closed_at: datetime | None
    messages: List[TicketMessageResponse] = []
    events: List[TicketEventResponse] = []
    class Config: from_attributes = True


# --- Endpoints ---

@router.post("/tickets", response_model=TicketResponse)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID required")

    # Validate Order
    order = db.query(models.Order).filter(
        models.Order.id == payload.order_id,
        models.Order.user_id == user_id,
        models.Order.is_deleted == False
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found or you don't have permission")

    ticket = models.SupportTicket(
        user_id=user_id,
        order_id=order.id,
        organization_id=order.organization_id,
        issue_type=payload.issue_type,
        status="open",
        priority=payload.priority
    )
    db.add(ticket)
    db.flush()

    # Log event
    event = models.TicketEvent(
        ticket_id=ticket.id,
        old_status=None,
        new_status="open",
        changed_by=user_id
    )
    db.add(event)

    # Notify seller
    notif = models.Notification(
        user_id=order.organization.owner_id if hasattr(order.organization, 'owner_id') else 1, # fallback if owner_id missing
        type="ticket_created",
        title="New Support Ticket",
        message=f"Ticket #{ticket.id} opened for Order #{order.id} ({payload.issue_type})",
        priority=payload.priority
    )
    db.add(notif)
    db.commit()
    db.refresh(ticket)
    return ticket

@router.get("/tickets", response_model=List[TicketResponse])
def get_tickets(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id")
    org_id = _org_id(current_user)
    business_type = current_user.get("business_type", "customer")

    if business_type == "customer":
        # Buyer sees their tickets
        tickets = db.query(models.SupportTicket).filter(models.SupportTicket.user_id == user_id).order_by(models.SupportTicket.created_at.desc()).all()
    else:
        # Seller sees org tickets
        tickets = db.query(models.SupportTicket).filter(models.SupportTicket.organization_id == org_id).order_by(models.SupportTicket.created_at.desc()).all()
    
    return tickets

@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id")
    org_id = _org_id(current_user)

    ticket = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == ticket_id,
        or_(models.SupportTicket.user_id == user_id, models.SupportTicket.organization_id == org_id)
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@router.post("/tickets/{ticket_id}/message", response_model=TicketMessageResponse)
def add_ticket_message(ticket_id: int, payload: TicketMessageCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id")
    org_id = _org_id(current_user)

    ticket = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == ticket_id,
        or_(models.SupportTicket.user_id == user_id, models.SupportTicket.organization_id == org_id)
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    if ticket.status == "resolved":
        raise HTTPException(status_code=400, detail="Cannot add message to a resolved ticket")

    msg = models.TicketMessage(
        ticket_id=ticket.id,
        sender_id=user_id,
        message=payload.message
    )
    db.add(msg)

    # Notify other party
    if user_id == ticket.user_id:
        # Buyer sent message -> Notify Seller
        notify_user_id = ticket.organization.owner_id if hasattr(ticket.organization, 'owner_id') else 1
    else:
        # Seller sent message -> Notify Buyer
        notify_user_id = ticket.user_id
    
    if notify_user_id:
        notif = models.Notification(
            user_id=notify_user_id,
            type="ticket_message",
            title=f"New message on Ticket #{ticket.id}",
            message=payload.message[:50] + "...",
            priority="medium"
        )
        db.add(notif)

    db.commit()
    db.refresh(msg)
    return msg

@router.patch("/tickets/{ticket_id}/status", response_model=TicketResponse)
def update_ticket_status(ticket_id: int, payload: TicketStatusUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id")
    org_id = _org_id(current_user)
    business_type = current_user.get("business_type", "customer")

    if business_type == "customer":
        raise HTTPException(status_code=403, detail="Only sellers/admins can update ticket status")

    ticket = db.query(models.SupportTicket).filter(
        models.SupportTicket.id == ticket_id,
        models.SupportTicket.organization_id == org_id
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    if payload.status not in ["open", "in_progress", "resolved"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    old_status = ticket.status
    if old_status != payload.status:
        ticket.status = payload.status
        if payload.status == "resolved":
            ticket.closed_at = datetime.utcnow()
        
        event = models.TicketEvent(
            ticket_id=ticket.id,
            old_status=old_status,
            new_status=payload.status,
            changed_by=user_id
        )
        db.add(event)

        # Notify buyer
        notif = models.Notification(
            user_id=ticket.user_id,
            type="ticket_status",
            title=f"Ticket #{ticket.id} status updated",
            message=f"Status changed to {payload.status}",
            priority="medium" if payload.status == "resolved" else "low"
        )
        db.add(notif)
        db.commit()
        db.refresh(ticket)
    return ticket
