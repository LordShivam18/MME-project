import os
import logging
import secrets
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models import core as models
from auth import pwd_context, create_access_token, create_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Config ---
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_SECONDS = 60
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


# --- Schemas ---
class SignupInitiate(BaseModel):
    email: str
    password: str = Field(..., min_length=8)

class OTPVerify(BaseModel):
    email: str
    otp: str = Field(..., min_length=6, max_length=6)
    password: str = Field(..., min_length=8)

class ForgotInitiate(BaseModel):
    email: str

class ForgotVerify(BaseModel):
    email: str
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)

class GoogleAuthPayload(BaseModel):
    id_token: str


# --- Helpers ---
def generate_otp() -> str:
    return f"{secrets.randbelow(900000) + 100000}"

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def verify_otp_hash(otp: str, hashed: str) -> bool:
    return hash_otp(otp) == hashed

def send_otp_email(email: str, otp: str, purpose: str):
    """Send OTP email. Raises RuntimeError if SMTP not configured or send fails."""
    if not SMTP_USER or not SMTP_PASS:
        logger.error("SMTP_FATAL: SMTP_USER or SMTP_PASS not set. Cannot send OTP to %s", email)
        raise RuntimeError("Email service not configured. Set SMTP_USER and SMTP_PASS environment variables.")
    
    subject = "Your Verification Code" if purpose == "signup" else "Password Reset Code"
    body = f"""
    <html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px;">
    <div style="max-width: 400px; margin: 0 auto; background: #f8fafc; border-radius: 12px; padding: 32px; border: 1px solid #e2e8f0;">
        <h2 style="color: #1e293b; margin-top: 0;">{subject}</h2>
        <p style="color: #475569;">Your verification code is:</p>
        <h1 style="color: #3b82f6; letter-spacing: 8px; text-align: center; font-size: 2rem; margin: 24px 0;">{otp}</h1>
        <p style="color: #64748b; font-size: 0.875rem;">This code expires in {OTP_EXPIRY_MINUTES} minutes.</p>
        <p style="color: #94a3b8; font-size: 0.75rem;">If you didn't request this, please ignore this email.</p>
    </div>
    </body></html>
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = email
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, email, msg.as_string())
        logger.info("SMTP_OK: OTP email sent to %s", email)
    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP_AUTH_FAIL: %s", str(e))
        raise RuntimeError("Email authentication failed. Check SMTP_USER and SMTP_PASS.")
    except smtplib.SMTPException as e:
        logger.error("SMTP_ERROR: %s", str(e))
        raise RuntimeError(f"Email delivery failed: {str(e)}")
    except Exception as e:
        logger.error("SMTP_UNEXPECTED: %s", str(e))
        raise RuntimeError(f"Email service error: {str(e)}")

def _create_user_tokens(user, db: Session):
    token_data = {
        "sub": user.email,
        "user_id": user.id,
        "organization_id": user.organization_id,
        "token_version": user.token_version
    }
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    user.hashed_refresh_token = pwd_context.hash(refresh_token)
    db.commit()
    return access_token, refresh_token


# ============================================================
# SIGNUP
# ============================================================
@router.post("/auth/signup/initiate")
def signup_initiate(payload: SignupInitiate, db: Session = Depends(get_db)):
    """Step 1: Send OTP to email for signup verification."""
    try:
        logger.info("SIGNUP_INITIATE: email=%s", payload.email)
        
        # Cooldown
        recent = db.query(models.OTPCode).filter(
            models.OTPCode.email == payload.email,
            models.OTPCode.purpose == "signup",
            models.OTPCode.created_at >= datetime.utcnow() - timedelta(seconds=OTP_COOLDOWN_SECONDS)
        ).first()
        if recent:
            raise HTTPException(status_code=429, detail="Please wait before requesting another code")
        
        # Generic response whether user exists or not (prevent enumeration)
        existing = db.query(models.User).filter(models.User.email == payload.email).first()
        if existing:
            logger.info("SIGNUP_INITIATE: user already exists, returning generic response")
            return {"message": "If this email is available, a verification code has been sent."}
        
        otp = generate_otp()
        logger.info("SIGNUP_INITIATE: OTP generated for %s", payload.email)
        
        # Invalidate old OTPs
        db.query(models.OTPCode).filter(
            models.OTPCode.email == payload.email,
            models.OTPCode.purpose == "signup"
        ).delete()
        
        otp_record = models.OTPCode(
            email=payload.email,
            hashed_otp=hash_otp(otp),
            purpose="signup",
            expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
        )
        db.add(otp_record)
        db.commit()
        
        send_otp_email(payload.email, otp, "signup")
        logger.info("SIGNUP_INITIATE: OTP email sent for %s", payload.email)
        
        return {"message": "If this email is available, a verification code has been sent."}
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error("SIGNUP_INITIATE_SMTP: %s", str(e))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("SIGNUP_INITIATE_ERROR: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal auth error")


@router.post("/auth/signup/verify")
def signup_verify(payload: OTPVerify, db: Session = Depends(get_db)):
    """Step 2: Verify OTP and create account."""
    try:
        logger.info("SIGNUP_VERIFY: email=%s", payload.email)
        
        otp_record = db.query(models.OTPCode).filter(
            models.OTPCode.email == payload.email,
            models.OTPCode.purpose == "signup"
        ).order_by(models.OTPCode.created_at.desc()).first()
        
        if not otp_record:
            raise HTTPException(status_code=400, detail="No verification pending for this email")
        
        if datetime.utcnow() > otp_record.expires_at:
            db.delete(otp_record)
            db.commit()
            raise HTTPException(status_code=400, detail="Verification code expired")
        
        if otp_record.attempts >= OTP_MAX_ATTEMPTS:
            db.delete(otp_record)
            db.commit()
            raise HTTPException(status_code=400, detail="Too many attempts. Request a new code.")
        
        otp_record.attempts += 1
        if not verify_otp_hash(payload.otp, otp_record.hashed_otp):
            db.commit()
            raise HTTPException(status_code=400, detail="Invalid verification code")
        
        # Race condition guard
        existing = db.query(models.User).filter(models.User.email == payload.email).first()
        if existing:
            db.delete(otp_record)
            db.commit()
            raise HTTPException(status_code=400, detail="Account already exists")
        
        # Create user + default org
        org = models.Organization(name=f"{payload.email.split('@')[0]}'s Organization")
        db.add(org)
        db.flush()
        
        user = models.User(
            email=payload.email,
            hashed_password=pwd_context.hash(payload.password),
            organization_id=org.id,
            role="admin"
        )
        db.add(user)
        
        # Create free subscription
        sub = models.Subscription(organization_id=org.id, plan="free", status="active")
        db.add(sub)
        
        db.delete(otp_record)
        db.commit()
        db.refresh(user)
        
        logger.info("SIGNUP_VERIFY: user created id=%s, org=%s", user.id, org.id)
        
        access_token, refresh_token = _create_user_tokens(user, db)
        
        logger.info("SIGNUP_VERIFY: auto-login tokens created for %s", user.email)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "message": "Account created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("SIGNUP_VERIFY_ERROR: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal auth error")


# ============================================================
# FORGOT PASSWORD
# ============================================================
@router.post("/auth/forgot/initiate")
def forgot_initiate(payload: ForgotInitiate, db: Session = Depends(get_db)):
    """Send OTP for password reset."""
    try:
        logger.info("FORGOT_INITIATE: email=%s", payload.email)
        
        # Cooldown
        recent = db.query(models.OTPCode).filter(
            models.OTPCode.email == payload.email,
            models.OTPCode.purpose == "forgot_password",
            models.OTPCode.created_at >= datetime.utcnow() - timedelta(seconds=OTP_COOLDOWN_SECONDS)
        ).first()
        if recent:
            raise HTTPException(status_code=429, detail="Please wait before requesting another code")
        
        # Always generic response
        user = db.query(models.User).filter(models.User.email == payload.email).first()
        
        if user:
            otp = generate_otp()
            logger.info("FORGOT_INITIATE: OTP generated for %s", payload.email)
            
            db.query(models.OTPCode).filter(
                models.OTPCode.email == payload.email,
                models.OTPCode.purpose == "forgot_password"
            ).delete()
            
            otp_record = models.OTPCode(
                email=payload.email,
                hashed_otp=hash_otp(otp),
                purpose="forgot_password",
                expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
            )
            db.add(otp_record)
            db.commit()
            
            send_otp_email(payload.email, otp, "forgot_password")
            logger.info("FORGOT_INITIATE: OTP email sent for %s", payload.email)
        else:
            logger.info("FORGOT_INITIATE: no user found for %s (returning generic)", payload.email)
        
        return {"message": "If an account exists, a reset code has been sent."}
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error("FORGOT_INITIATE_SMTP: %s", str(e))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("FORGOT_INITIATE_ERROR: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal auth error")


@router.post("/auth/forgot/verify")
def forgot_verify(payload: ForgotVerify, db: Session = Depends(get_db)):
    """Verify OTP and reset password."""
    try:
        logger.info("FORGOT_VERIFY: email=%s", payload.email)
        
        otp_record = db.query(models.OTPCode).filter(
            models.OTPCode.email == payload.email,
            models.OTPCode.purpose == "forgot_password"
        ).order_by(models.OTPCode.created_at.desc()).first()
        
        if not otp_record:
            raise HTTPException(status_code=400, detail="No reset pending for this email")
        
        if datetime.utcnow() > otp_record.expires_at:
            db.delete(otp_record)
            db.commit()
            raise HTTPException(status_code=400, detail="Reset code expired")
        
        if otp_record.attempts >= OTP_MAX_ATTEMPTS:
            db.delete(otp_record)
            db.commit()
            raise HTTPException(status_code=400, detail="Too many attempts. Request a new code.")
        
        otp_record.attempts += 1
        if not verify_otp_hash(payload.otp, otp_record.hashed_otp):
            db.commit()
            raise HTTPException(status_code=400, detail="Invalid reset code")
        
        user = db.query(models.User).filter(models.User.email == payload.email).first()
        if not user:
            db.delete(otp_record)
            db.commit()
            raise HTTPException(status_code=400, detail="Account not found")
        
        # Update password
        user.hashed_password = pwd_context.hash(payload.new_password)
        # Invalidate refresh tokens
        user.token_version += 1
        user.hashed_refresh_token = None
        
        db.delete(otp_record)
        db.commit()
        
        logger.info("FORGOT_VERIFY: password reset completed for %s", payload.email)
        return {"message": "Password reset successful. Please login with your new password."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("FORGOT_VERIFY_ERROR: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal auth error")


# ============================================================
# GOOGLE OAUTH
# ============================================================
@router.post("/auth/google")
def google_auth(payload: GoogleAuthPayload, db: Session = Depends(get_db)):
    """Verify Google ID token, login or create user with smart account merge."""
    try:
        # --- Step 1: Verify Google token ---
        if not GOOGLE_CLIENT_ID:
            logger.error("GOOGLE_AUTH: GOOGLE_CLIENT_ID not set")
            raise HTTPException(status_code=503, detail="Google login not configured on this server")
        
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
        except ImportError:
            logger.error("GOOGLE_AUTH: google-auth package not installed")
            raise HTTPException(status_code=503, detail="Google auth not available on this server")
        
        try:
            idinfo = id_token.verify_oauth2_token(
                payload.id_token,
                google_requests.Request(),
                GOOGLE_CLIENT_ID
            )
        except ValueError as e:
            logger.warning("GOOGLE_AUTH: invalid token - %s", str(e))
            raise HTTPException(status_code=400, detail="Invalid or expired Google token")
        
        email = idinfo.get("email")
        name = idinfo.get("name", "")
        picture = idinfo.get("picture", "")
        
        if not email:
            raise HTTPException(status_code=400, detail="Google account has no email")
        
        logger.info("GOOGLE_AUTH: verified token for %s", email)
        
        # --- Step 2: Smart account merge ---
        user = db.query(models.User).filter(models.User.email == email).first()
        
        if user:
            # Existing user — merge Google profile data if missing
            updated = False
            if name and not user.full_name:
                user.full_name = name
                updated = True
            if picture and not user.avatar_url:
                user.avatar_url = picture
                updated = True
            if not user.username:
                user.username = email.split("@")[0]
                updated = True
            if updated:
                db.commit()
            logger.info("GOOGLE_AUTH: existing user login + merge (id=%s)", user.id)
        else:
            # New user — create org + user + subscription
            org = models.Organization(name=f"{name or email.split('@')[0]}'s Organization")
            db.add(org)
            db.flush()
            
            user = models.User(
                email=email,
                username=email.split("@")[0],
                full_name=name or None,
                avatar_url=picture or None,
                hashed_password=None,  # OAuth-only user, no password
                organization_id=org.id,
                role="admin"
            )
            db.add(user)
            
            sub = models.Subscription(organization_id=org.id, plan="free", status="active")
            db.add(sub)
            
            db.commit()
            db.refresh(user)
            logger.info("GOOGLE_AUTH: new user created id=%s, org=%s", user.id, org.id)
        
        # --- Step 3: Generate tokens ---
        access_token, refresh_token = _create_user_tokens(user, db)
        
        logger.info("GOOGLE_AUTH: tokens created for %s", email)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("GOOGLE_AUTH_ERROR: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Google login failed")
