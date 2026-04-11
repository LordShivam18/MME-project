import logging
import time
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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

# ---------------- APP INIT ----------------
app = FastAPI(
    title="Inventory & Demand Prediction API",
    version="1.0.0"
)

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change later to frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- RATE LIMITER ----------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------- STARTUP CHECK ----------------
@app.on_event("startup")
def startup():
    import models.core   # force model registration
    from database import Base, engine, SessionLocal
    from passlib.context import CryptContext

    try:
        print("Connecting to database...")
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully")
    except Exception as e:
        print("Database initialization failed:", str(e))
        return

    db = SessionLocal()
    try:
        print("Seeding user started")
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        user = db.query(models.core.User).filter(models.core.User.email == "test@gmail.com").first()
        
        if not user:
            hashed_pw = pwd_context.hash("123456")
            new_user = models.core.User(email="test@gmail.com", hashed_password=hashed_pw)
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            print("User created successfully")
        else:
            print("User already exists")
            
    except Exception as e:
        db.rollback()
        print("Seeding error:", e)
    finally:
        db.close()

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