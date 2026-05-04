from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List, Optional
from datetime import datetime, timedelta
import re
import time
import logging

logger = logging.getLogger(__name__)

# --- In-memory metrics cache (org-scoped, 60s TTL) ---
_metrics_cache: dict[int, dict] = {}  # {org_id: {"data": {...}, "expires_at": float}}

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
    priority: Optional[str] = None  # Auto-assigned if not provided
    sub_reason: Optional[str] = None

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
    attachment_url: str | None = None
    created_at: datetime
    class Config: from_attributes = True

class TicketResponse(BaseModel):
    id: int
    user_id: int
    order_id: int
    organization_id: int
    issue_type: str
    sub_reason: str | None = None
    status: str
    priority: str
    created_at: datetime
    closed_at: datetime | None
    first_response_at: datetime | None = None
    resolved_at: datetime | None = None
    sla_breached: bool = False
    escalated: bool = False
    sla_status: str | None = None  # Computed: "ok" | "breached"
    first_response_missed: bool = False  # Computed: no response + SLA breached
    messages: List[TicketMessageResponse] = []
    events: List[TicketEventResponse] = []
    class Config: from_attributes = True


# --- Priority Auto-Assignment ---
PRIORITY_MAP = {
    "refund": "high",
    "damaged": "medium",
    "wrong_item": "medium",
    "delayed": "low",
    "other": "low",
}

def _auto_priority(issue_type: str) -> str:
    return PRIORITY_MAP.get(issue_type, "low")


# --- Helpers ---
def _check_sla_and_escalation(db: Session, ticket):
    """Evaluate SLA breach (24h) and escalation (3 days) for a single ticket."""
    if ticket.status == "resolved":
        return
    now = datetime.utcnow()
    changed = False

    # SLA Breach: no seller response within 24h
    if not ticket.first_response_at and ticket.created_at < now - timedelta(hours=24):
        if not ticket.sla_breached:
            ticket.sla_breached = True
            changed = True

    # Escalation: unresolved after 3 days
    if ticket.created_at < now - timedelta(days=3):
        if not ticket.escalated:
            ticket.escalated = True
            ticket.priority = "high"
            changed = True
            logger.info(f"Ticket #{ticket.id} escalated after 3 days")

            # --- Escalation Notifications ---
            try:
                # Notify seller/admin
                seller_id = ticket.organization.owner_id if hasattr(ticket.organization, 'owner_id') else None
                if seller_id:
                    db.add(models.Notification(
                        user_id=seller_id,
                        type="support_escalation",
                        title=f"Ticket #{ticket.id} Escalated",
                        message=f"Ticket #{ticket.id} has been escalated due to delay",
                        priority="high"
                    ))
                # Notify buyer
                db.add(models.Notification(
                    user_id=ticket.user_id,
                    type="support_escalation",
                    title=f"Ticket #{ticket.id} Escalated",
                    message=f"Ticket #{ticket.id} has been escalated due to delay",
                    priority="high"
                ))
            except Exception as e:
                logger.warning(f"Failed to send escalation notifications for ticket #{ticket.id}: {e}")

    if changed:
        db.flush()


def auto_close_inactive_tickets(db: Session, ticket=None, tickets=None):
    """Option A implementation: auto-close tickets inactive for 7 days during fetch.
    Also evaluates SLA breach and escalation on every active ticket."""
    target_tickets = []
    if ticket: target_tickets.append(ticket)
    if tickets: target_tickets.extend(tickets)
    
    threshold = datetime.utcnow() - timedelta(days=7)
    changed = False
    
    for t in target_tickets:
        if t.status == "resolved":
            continue

        # Evaluate SLA & escalation first
        _check_sla_and_escalation(db, t)
        
        # Determine last activity
        last_msg = max(t.messages, key=lambda m: m.created_at, default=None)
        last_activity = last_msg.created_at if last_msg else t.created_at
        
        if last_activity < threshold:
            old_status = t.status
            t.status = "resolved"
            t.closed_at = datetime.utcnow()
            t.resolved_at = datetime.utcnow()
            
            event = models.TicketEvent(
                ticket_id=t.id,
                old_status=old_status,
                new_status="resolved",
                changed_by=0  # System auto-close
            )
            db.add(event)
            changed = True
            
    if changed:
        db.commit()


def _enrich_ticket_response(ticket) -> dict:
    """Add computed fields to ticket before returning."""
    ticket.sla_status = "breached" if ticket.sla_breached else "ok"
    ticket.first_response_missed = (ticket.first_response_at is None and ticket.sla_breached)
    return ticket


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

    # Prevent duplicate active tickets
    existing = db.query(models.SupportTicket).filter(
        models.SupportTicket.order_id == payload.order_id,
        models.SupportTicket.user_id == user_id,
        models.SupportTicket.status != "resolved"
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="An active ticket already exists for this order")

    # Priority auto-assignment
    effective_priority = payload.priority if payload.priority else _auto_priority(payload.issue_type)

    ticket = models.SupportTicket(
        user_id=user_id,
        order_id=order.id,
        organization_id=order.organization_id,
        issue_type=payload.issue_type,
        sub_reason=payload.sub_reason,
        status="open",
        priority=effective_priority
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
        user_id=order.organization.owner_id if hasattr(order.organization, 'owner_id') else 1,
        type="ticket_created",
        title="New Support Ticket",
        message=f"Ticket #{ticket.id} opened for Order #{order.id} ({payload.issue_type})",
        priority=effective_priority
    )
    db.add(notif)
    db.commit()
    db.refresh(ticket)
    return _enrich_ticket_response(ticket)

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
    
    auto_close_inactive_tickets(db, tickets=tickets)
    return [_enrich_ticket_response(t) for t in tickets]

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
    
    auto_close_inactive_tickets(db, ticket=ticket)
    return _enrich_ticket_response(ticket)

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

    if len(payload.message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long")

    # Sanitize message
    safe_message = re.sub(r'<[^>]*>', '', payload.message).strip()
    if not safe_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    msg = models.TicketMessage(
        ticket_id=ticket.id,
        sender_id=user_id,
        message=safe_message
    )
    db.add(msg)

    # SLA Tracking: First response from seller
    if user_id != ticket.user_id and not ticket.first_response_at:
        ticket.first_response_at = datetime.utcnow()

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
            ticket.resolved_at = datetime.utcnow()
        
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
    return _enrich_ticket_response(ticket)


# ============================================================
# SUPPORT ANALYTICS ENDPOINT
# ============================================================
@router.get("/support/metrics")
def get_support_metrics(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Return operational SLA metrics scoped by organization with 60s in-memory cache."""
    org_id = _org_id(current_user)
    business_type = current_user.get("business_type", "customer")

    if business_type == "customer":
        raise HTTPException(status_code=403, detail="Only organization users can view support metrics")

    # --- Cache check (org-scoped, 60s TTL) ---
    now = time.time()
    cached = _metrics_cache.get(org_id)
    if cached and cached["expires_at"] > now:
        return cached["data"]

    # --- Compute metrics ---
    base = db.query(models.SupportTicket).filter(models.SupportTicket.organization_id == org_id)
    total = base.count()

    if total == 0:
        result = {
            "total_tickets": 0,
            "open_tickets": 0,
            "avg_response_time_hours": 0.0,
            "avg_resolution_time_hours": 0.0,
            "sla_breach_rate": 0.0,
            "escalation_rate": 0.0,
            "cached": False,
        }
        _metrics_cache[org_id] = {"data": result, "expires_at": now + 60}
        return result

    open_tickets = base.filter(models.SupportTicket.status != "resolved").count()
    breached = base.filter(models.SupportTicket.sla_breached == True).count()
    escalated = base.filter(models.SupportTicket.escalated == True).count()

    # Avg first response time (only tickets that have been responded to)
    responded = base.filter(models.SupportTicket.first_response_at.isnot(None)).all()
    if responded:
        avg_response_seconds = sum(
            (t.first_response_at - t.created_at).total_seconds() for t in responded
        ) / len(responded)
        avg_response_hours = round(avg_response_seconds / 3600, 2)
    else:
        avg_response_hours = 0.0

    # Avg resolution time (only resolved tickets)
    resolved = base.filter(models.SupportTicket.resolved_at.isnot(None)).all()
    if resolved:
        avg_resolution_seconds = sum(
            (t.resolved_at - t.created_at).total_seconds() for t in resolved
        ) / len(resolved)
        avg_resolution_hours = round(avg_resolution_seconds / 3600, 2)
    else:
        avg_resolution_hours = 0.0

    result = {
        "total_tickets": total,
        "open_tickets": open_tickets,
        "avg_response_time_hours": avg_response_hours,
        "avg_resolution_time_hours": avg_resolution_hours,
        "sla_breach_rate": round(breached / total, 4) if total else 0.0,
        "escalation_rate": round(escalated / total, 4) if total else 0.0,
        "cached": False,
    }

    # Store in cache with 60s TTL
    _metrics_cache[org_id] = {"data": result, "expires_at": now + 60}
    return result
