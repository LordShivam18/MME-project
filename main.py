import logging
import time
from fastapi import FastAPI, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from database import engine
from models.core import Base
from routers import endpoints
from limiter import limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(
    title="Inventory & Demand Prediction API",
    version="1.0.0"
)

# Render Deployment CORS Handler
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Expand this to exact frontend vercel/render URL in deep production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach Limiter to FastAPI state and register exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"API Request: {request.method} {request.url.path} - Status: {response.status_code} - Loaded in: {process_time:.4f}s")
        return response
    except Exception as exc:
        process_time = time.time() - start_time
        logger.error(f"FATAL API CRASH: {request.method} {request.url.path} - Error: {str(exc)}")
        raise

app.include_router(endpoints.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok"}
