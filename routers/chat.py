import logging
import html
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from database import get_db
from models import core as models
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

def _org_id(current_user: dict) -> int:
    return current_user.get("organization_id") or 0

# --- Schemas ---
class ConversationCreate(BaseModel):
    contact_id: int

class MessageCreate(BaseModel):
    conversation_id: int
    content: str = Field(..., min_length=1, max_length=2048)

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender_user_id: int
    sender_email: Optional[str] = None
    content: str
    is_read: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    id: int
    organization_id: int
    contact_id: Optional[int] = None
    contact_name: Optional[str] = None
    created_at: datetime
    last_message_at: datetime
    last_message_preview: Optional[str] = None
    unread_count: int = 0
    class Config:
        from_attributes = True


# ============================================================
# CONVERSATIONS
# ============================================================
@router.get("/conversations")
def get_conversations(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    convos = db.query(models.Conversation).filter(
        models.Conversation.organization_id == org_id,
        models.Conversation.is_deleted == False
    ).order_by(models.Conversation.last_message_at.desc()).limit(20).all()
    
    result = []
    for c in convos:
        # Last message preview
        last_msg = db.query(models.Message).filter(
            models.Message.conversation_id == c.id
        ).order_by(models.Message.created_at.desc()).first()
        
        # Unread count
        unread = db.query(func.count(models.Message.id)).filter(
            models.Message.conversation_id == c.id,
            models.Message.is_read == False,
            models.Message.sender_user_id != current_user["user_id"]
        ).scalar() or 0
        
        result.append({
            "id": c.id,
            "organization_id": c.organization_id,
            "contact_id": c.contact_id,
            "contact_name": c.contact.name if c.contact else "Internal",
            "created_at": c.created_at,
            "last_message_at": c.last_message_at,
            "last_message_preview": (last_msg.content[:80] + "...") if last_msg and len(last_msg.content) > 80 else (last_msg.content if last_msg else None),
            "unread_count": unread
        })
    
    return result


@router.post("/conversations")
def create_or_get_conversation(payload: ConversationCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    if not payload.contact_id:
        raise HTTPException(status_code=400, detail="contact_id is required")
    
    try:
        # Verify contact belongs to this org
        contact = db.query(models.Contact).filter(
            models.Contact.id == payload.contact_id,
            models.Contact.organization_id == org_id
        ).first()
        if not contact:
            logger.warning(f"Chat: contact {payload.contact_id} not found for org {org_id}")
            raise HTTPException(status_code=404, detail="Contact not found in your organization")
        
        # Idempotent: return existing conversation if one exists
        existing = db.query(models.Conversation).filter(
            models.Conversation.organization_id == org_id,
            models.Conversation.contact_id == payload.contact_id,
            models.Conversation.is_deleted == False
        ).first()
        
        if existing:
            logger.info(f"Chat: returning existing conversation {existing.id} for contact {contact.name}")
            return {"id": existing.id, "contact_name": contact.name, "created": False}
        
        convo = models.Conversation(
            organization_id=org_id,
            contact_id=payload.contact_id,
            last_message_at=datetime.utcnow()
        )
        db.add(convo)
        db.commit()
        db.refresh(convo)
        logger.info(f"Chat: created conversation {convo.id} for contact {contact.name}")
        return {"id": convo.id, "contact_name": contact.name, "created": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat: failed to create conversation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")


# ============================================================
# MESSAGES
# ============================================================
@router.get("/messages/{conversation_id}")
def get_messages(conversation_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    # Verify conversation belongs to org
    convo = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id,
        models.Conversation.organization_id == org_id,
        models.Conversation.is_deleted == False
    ).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = db.query(models.Message).filter(
        models.Message.conversation_id == conversation_id
    ).order_by(models.Message.created_at.asc()).limit(50).all()
    
    result = []
    for m in messages:
        result.append({
            "id": m.id,
            "conversation_id": m.conversation_id,
            "sender_user_id": m.sender_user_id,
            "sender_email": m.sender.email if m.sender else None,
            "content": m.content,
            "is_read": m.is_read,
            "created_at": m.created_at
        })
    
    return result


@router.post("/messages")
def send_message(payload: MessageCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    # Verify conversation belongs to org
    convo = db.query(models.Conversation).filter(
        models.Conversation.id == payload.conversation_id,
        models.Conversation.organization_id == org_id,
        models.Conversation.is_deleted == False
    ).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Sanitize content (strip HTML)
    clean_content = html.escape(payload.content.strip())
    if not clean_content:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    msg = models.Message(
        conversation_id=payload.conversation_id,
        sender_user_id=current_user["user_id"],
        content=clean_content
    )
    db.add(msg)
    
    # Update conversation timestamp
    convo.last_message_at = datetime.utcnow()
    
    db.commit()
    db.refresh(msg)
    
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_user_id": msg.sender_user_id,
        "content": msg.content,
        "is_read": msg.is_read,
        "created_at": msg.created_at
    }


@router.patch("/messages/{conversation_id}/read")
def mark_messages_read(conversation_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    org_id = _org_id(current_user)
    
    # Verify conversation belongs to org
    convo = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id,
        models.Conversation.organization_id == org_id
    ).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    db.query(models.Message).filter(
        models.Message.conversation_id == conversation_id,
        models.Message.sender_user_id != current_user["user_id"],
        models.Message.is_read == False
    ).update({"is_read": True})
    db.commit()
    
    return {"message": "Messages marked as read"}
