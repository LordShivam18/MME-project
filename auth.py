import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_dev_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# ---------------- PASSWORD HASHING ----------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------- OAUTH2 SCHEME ----------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


# ---------------- TOKEN CREATION ----------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ---------------- TOKEN DECODE ----------------
def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------- DEPENDENCY: get_current_user ----------------
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Extract Bearer token, decode JWT, validate it's an access token,
    look up user in DB, and return a dict with user info.
    Raises 401 if anything is invalid.
    """
    payload = decode_token(token)

    # Ensure this is an access token, not a refresh token
    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email: str = payload.get("sub")
    user_id: int = payload.get("user_id")

    if email is None or user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user still exists in DB
    from models.core import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"user_id": user.id, "email": user.email, "organization_id": user.organization_id, "role": "shop_owner"}


# ---------------- RATE LIMIT KEY ----------------
def rate_limit_key_func(request: Request) -> str:
    """
    Custom Rate Limiter Key Function for SlowAPI.
    Checks for the Authorization header. If present, hashes the bearer token/user lookup.
    If missing (Unauthenticated), falls back to the raw IP address.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            uid = payload.get("user_id", "unknown")
            return f"user:{uid}"
        except JWTError:
            pass

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0]}"
    return f"ip:{request.client.host}"
