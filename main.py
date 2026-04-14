import logging
import time
import os
import traceback

print("App starting...")

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from database import engine

print("Imports successful")

from routers import endpoints
from limiter import limiter

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ---------------- LIFESPAN ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 STARTUP RUNNING")
    import models.core   # force model registration
    from database import Base, engine, SessionLocal
    from models.core import User
    from auth import pwd_context

    print("Connecting to DB...")
    Base.metadata.create_all(bind=engine)
    print("DB connection successful")
    
    print("Starting seeding process...")
    db = SessionLocal()

    user = db.query(User).filter(User.email == "test@gmail.com").first()

    if not user:
        print("User not found. Creating...")

        hashed = pwd_context.hash("Test@123456")

        new_user = User(
            email="test@gmail.com",
            hashed_password=hashed
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        print("✅ User created:", new_user.email)
    else:
        print("⚠️ User already exists")

    db.close()
        
    yield

# ---------------- APP INIT ----------------
app = FastAPI(
    title="Inventory & Demand Prediction API",
    version="1.0.0",
    lifespan=lifespan
)

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- RATE LIMITER ----------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------- REQUEST LOGGER ----------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            f"{request.method} {request.url.path} "
            f"{response.status_code} {process_time:.4f}s"
        )
        return response
    except Exception as exc:
        process_time = time.time() - start_time
        logger.error(
            f"CRASH: {request.method} {request.url.path} - {str(exc)}"
        )
        raise

# ---------------- ROUTES ----------------
app.include_router(endpoints.router, prefix="/api/v1")

# ---------------- HEALTH CHECK ----------------
@app.get("/health")
def health_check():
    return {"status": "ok"}