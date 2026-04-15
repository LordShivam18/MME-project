import logging
import time
import os
import traceback

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from database import engine
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
    logger.info("🚀 STARTUP RUNNING")
    import models.core   # force model registration
    from database import Base, engine, SessionLocal
    from models.core import User
    from auth import pwd_context

    logger.info("Connecting to DB...")
    Base.metadata.create_all(bind=engine)
    logger.info("DB connection successful")
    
    logger.info("Starting seeding process...")
    db = SessionLocal()

    user = db.query(User).filter(User.email == "test@gmail.com").first()

    if not user:
        logger.info("User not found. Creating...")

        hashed = pwd_context.hash("123456")

        new_user = User(
            email="test@gmail.com",
            hashed_password=hashed
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info("✅ User created: %s", new_user.email)
    else:
        logger.info("⚠️ User already exists. Ensuring password is set to 123456.")
        user.hashed_password = pwd_context.hash("123456")
        db.commit()

    db.close()
        
    yield

# ---------------- APP INIT ----------------
app = FastAPI(
    title="Inventory & Demand Prediction API",
    version="1.0.0",
    lifespan=lifespan
)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "https://mme-project.vercel.app",
    "https://mme-project-p1qd0jd48-shivam-chourasias-projects.vercel.app"
]

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- EXCEPTION HANDLER ----------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin")
    headers = {}
    if origin in ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
        headers=headers
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