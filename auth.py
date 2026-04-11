import time
from typing import Optional
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# In a real app, this should securely generate/parse cryptographically signed JWT strings.
# For this MVP skeleton, we mock the parsing structure to demonstrate the dependency pattern.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")

def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Validates the JWT token.
    If valid, returns the user ID (extrapolated from the JWT payload).
    """
    if not token or token == "invalid":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Mocking JWT decode: In reality, decode the token payload.
    # Return user_id 1 for structurally valid MVP token.
    return {"user_id": 1, "role": "shop_owner"}


def rate_limit_key_func(request: Request) -> str:
    """
    Custom Rate Limiter Key Function for SlowAPI.
    Checks for the Authorization header. If present, hashes the bearer token/user lookup.
    If missing (Unauthenticated), falls back to the raw IP address.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        # In a production app, decode the token rapidly here without DB lookups
        # So we key rate limits directly by JWT user_id payload.
        # Format: token[:10] stands in for user_id payload here.
        return f"user:{token[:10]}"
        
    # Unauthenticated Fallback -> Route them by IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0]}"
    return f"ip:{request.client.host}"

import re
from hashlib import sha256
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def validate_password(password: str) -> None:
    if " " in password:
        raise ValueError("Password cannot contain spaces.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ValueError("Password must contain at least one special character.")

def preprocess_password(password: str) -> str:
    """Pre-hashes the password using SHA-256 to safely bypass bcrypt's 72-byte limit."""
    return sha256(password.encode()).hexdigest()
