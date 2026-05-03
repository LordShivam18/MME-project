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
    from models.core import User, Organization
    from auth import pwd_context

    logger.info("Connecting to DB...")
    Base.metadata.create_all(bind=engine)
    logger.info("DB connection successful")
    
    # Migrate: add columns if they don't exist (for existing DBs)
    try:
        with engine.connect() as conn:
            # --- OTP Codes table (required for signup/forgot password) ---
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS otp_codes (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR NOT NULL,
                    hashed_otp VARCHAR NOT NULL,
                    purpose VARCHAR NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    attempts INTEGER DEFAULT 0 NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_otp_codes_email ON otp_codes (email)"))
            logger.info("✅ otp_codes table ensured")
            # --- Users table ---
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_refresh_token VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id INTEGER"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR DEFAULT 'admin'"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT false"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_platform_admin BOOLEAN DEFAULT false"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR"))
            conn.execute(text("ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL"))
            # --- Organizations table ---
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT false"))
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS ai_decision_mode VARCHAR DEFAULT 'balanced'"))
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR"))
            # --- Products table ---
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT false"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS low_stock_threshold INTEGER DEFAULT 5"))
            # --- Products/Inventory indexes for public API performance ---
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_inventory_product_qty ON inventory(product_id, quantity_on_hand)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_updated_at ON products(updated_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_shop_deleted ON products(shop_id, is_deleted)"))
            # --- Inventory table ---
            conn.execute(text("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS created_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            # --- Sales table ---
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS created_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            # --- AuditLog indexes for pagination performance ---
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_org_created ON audit_logs (organization_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_org_action ON audit_logs (organization_id, action)"))
            # --- Organizations: Stripe customer link ---
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR"))
            # --- Stripe events idempotency table ---
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS stripe_events (
                    id SERIAL PRIMARY KEY,
                    event_id VARCHAR UNIQUE NOT NULL,
                    event_type VARCHAR NOT NULL,
                    organization_id INTEGER REFERENCES organizations(id),
                    status VARCHAR NOT NULL DEFAULT 'processed',
                    details VARCHAR,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_stripe_events_event_id ON stripe_events (event_id)"))
            # --- Chat tables ---
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    contact_id INTEGER REFERENCES contacts(id),
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_message_at TIMESTAMP DEFAULT NOW(),
                    is_deleted BOOLEAN DEFAULT FALSE
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_convos_org_last ON conversations (organization_id, last_message_at DESC)"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
                    sender_user_id INTEGER NOT NULL REFERENCES users(id),
                    content VARCHAR(2048) NOT NULL,
                    is_read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_msgs_convo_created ON messages (conversation_id, created_at DESC)"))
            # --- product_insights AI columns (idempotent) ---
            pi_columns = [
                ("demand_min", "FLOAT DEFAULT 0"),
                ("demand_max", "FLOAT DEFAULT 0"),
                ("stockout_risk", "FLOAT DEFAULT 0"),
                ("overstock_risk", "FLOAT DEFAULT 0"),
                ("is_dead_stock", "BOOLEAN DEFAULT FALSE"),
                ("anomaly_flags", "VARCHAR DEFAULT ''"),
                ("weekday_pattern", "TEXT"),
                ("product_behavior_profile", "TEXT"),
                ("last_profile_updated_at", "TIMESTAMP"),
                ("bias_factor", "FLOAT DEFAULT 0"),
                ("adaptive_alpha", "FLOAT DEFAULT 0.3"),
                ("priority_score", "FLOAT DEFAULT 0"),
                ("priority_demand_norm", "FLOAT DEFAULT 0"),
                ("priority_margin_norm", "FLOAT DEFAULT 0"),
                ("priority_risk_norm", "FLOAT DEFAULT 0"),
                ("explanation_points", "TEXT"),
                ("generated_at", "TIMESTAMP"),
                ("model_version", "VARCHAR DEFAULT '1.0.0'"),
            ]
            for col_name, col_type in pi_columns:
                try:
                    conn.execute(text(f"ALTER TABLE product_insights ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                except Exception:
                    pass  # Column may already exist
            # --- Performance indexes ---
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pi_product_org ON product_insights (product_id, organization_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_convos_org_contact ON conversations (organization_id, contact_id)"))
            # --- Pricing Engine tables ---
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pricing_tiers (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    shop_id INTEGER NOT NULL REFERENCES organizations(id),
                    min_qty INTEGER NOT NULL,
                    price_per_unit NUMERIC(10,2) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(product_id, min_qty)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pricing_tiers_product ON pricing_tiers (product_id, shop_id)"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS price_requests (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    shop_id INTEGER NOT NULL REFERENCES organizations(id),
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    quantity INTEGER NOT NULL,
                    requested_price NUMERIC(10,2) NOT NULL,
                    approved_price NUMERIC(10,2),
                    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
                    admin_note VARCHAR,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_price_requests_user_product ON price_requests (user_id, product_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_price_requests_shop_status ON price_requests (shop_id, status)"))
            # --- Pricing hardening: audit columns ---
            conn.execute(text("ALTER TABLE price_requests ADD COLUMN IF NOT EXISTS decided_by INTEGER"))
            conn.execute(text("ALTER TABLE price_requests ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP"))
            # --- Pricing hardening: optimized indexes (FIX 6) ---
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pr_status_created ON price_requests (status, created_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pr_product_user_created ON price_requests (product_id, user_id, created_at DESC)"))
            # --- Idempotency keys table ---
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    key VARCHAR NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP,
                    UNIQUE(user_id, key)
                )
            """))
            # --- Idempotency TTL column (FIX 1) ---
            conn.execute(text("ALTER TABLE idempotency_keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP"))
            # --- Order conversion columns (PART 2) ---
            conn.execute(text("ALTER TABLE price_requests ADD COLUMN IF NOT EXISTS order_id INTEGER"))
            conn.execute(text("ALTER TABLE orders ALTER COLUMN contact_id DROP NOT NULL"))
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS negotiation_request_id INTEGER"))
            # --- Partial index for pending requests (FIX 2) ---
            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pr_pending_only ON price_requests(product_id, user_id, created_at DESC) WHERE status = 'pending'"))
            except Exception:
                pass  # Partial indexes may not be supported on all PG versions
            # --- Elite hardening columns ---
            conn.execute(text("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS reserved_quantity INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE price_requests ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE price_requests ADD COLUMN IF NOT EXISTS negotiation_delta FLOAT"))
            # --- Role + KYC + Marketplace ---
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS business_type VARCHAR DEFAULT 'customer'"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_complete BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS category VARCHAR"))
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS address VARCHAR"))
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS phone VARCHAR"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_kyc (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
                    full_name VARCHAR NOT NULL,
                    age INTEGER,
                    phone VARCHAR,
                    email VARCHAR NOT NULL,
                    address VARCHAR,
                    business_type VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_kyc_user ON user_kyc (user_id)"))
            # --- Chat ↔ Order link ---
            conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS order_id INTEGER REFERENCES orders(id)"))
            # --- Trust + Reviews ---
            conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS trust_score FLOAT DEFAULT 0.0"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_blocked_at TIMESTAMP"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    store_id INTEGER NOT NULL REFERENCES organizations(id),
                    order_id INTEGER REFERENCES orders(id),
                    product_id INTEGER REFERENCES products(id),
                    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                    comment VARCHAR(1000),
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE (user_id, order_id)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reviews_store ON reviews (store_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reviews_user ON reviews (user_id)"))
            # --- Search performance: trigram index ---
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin (name gin_trgm_ops)"))
            except Exception:
                pass  # Extension may not be available in all environments
            # --- Verified reviews ---
            conn.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS verified_purchase BOOLEAN DEFAULT FALSE"))
            # --- Support Tickets ---
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_user ON orders (user_id)"))
            conn.commit()
        logger.info("Migration check complete: all columns, indexes, and tables ensured")
    except Exception as e:
        logger.warning("Migration note: %s", str(e))
    
    logger.info("Starting seeding process...")
    db = SessionLocal()

    try:
        # Ensure default organization exists
        default_org = db.query(Organization).filter(Organization.name == "Default Organization").first()
        if not default_org:
            default_org = Organization(name="Default Organization")
            db.add(default_org)
            db.commit()
            db.refresh(default_org)
            logger.info("✅ Default organization created: id=%s", default_org.id)
        else:
            logger.info("⚠️ Default organization already exists: id=%s", default_org.id)

        # 🔴 SaaS: Ensure default subscription exists for the default org
        from models.core import Subscription
        default_sub = db.query(Subscription).filter(Subscription.organization_id == default_org.id).first()
        if not default_sub:
            default_sub = Subscription(
                organization_id=default_org.id,
                plan="free",
                status="active"
            )
            db.add(default_sub)
            db.commit()
            logger.info("✅ Default 'free' subscription created for org: id=%s", default_org.id)


        # Ensure test user exists
        user = db.query(User).filter(User.email == "test@gmail.com").first()

        if not user:
            logger.info("User not found. Creating...")

            hashed = pwd_context.hash("123456")

            new_user = User(
                email="test@gmail.com",
                hashed_password=hashed,
                organization_id=default_org.id,
                kyc_complete=True,
                business_type="retailer",
            )

            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            logger.info("✅ User created: %s (org_id=%s)", new_user.email, new_user.organization_id)
        else:
            logger.info("⚠️ User already exists. Ensuring password and org assignment.")
            user.hashed_password = pwd_context.hash("123456")
            if not user.organization_id:
                user.organization_id = default_org.id
                logger.info("Assigned user to default org: id=%s", default_org.id)
            # Ensure existing admin has KYC complete
            user.kyc_complete = True
            user.business_type = "retailer"
            db.commit()

        # Ensure admin fallback user exists (idempotent)
        admin = db.query(User).filter(User.email == "admin@test.com").first()
        if not admin:
            admin = User(
                email="admin@test.com",
                username="admin",
                hashed_password=pwd_context.hash("admin123"),
                organization_id=default_org.id,
                role="admin",
                is_platform_admin=True
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            logger.info("✅ Admin user created: %s (org_id=%s)", admin.email, admin.organization_id)
        else:
            # Ensure password is correct and admin flags are set
            admin.hashed_password = pwd_context.hash("admin123")
            admin.is_platform_admin = True
            admin.role = "admin"
            if not admin.organization_id:
                admin.organization_id = default_org.id
            db.commit()
            logger.info("⚠️ Admin user already exists: %s (org_id=%s)", admin.email, admin.organization_id)

        # Migrate existing data: update shop_id references for existing products/inventory/sales
        # that may reference user.id instead of organization.id
        from models.core import Product, Inventory, Sale
        orphan_products = db.query(Product).filter(
            Product.shop_id != default_org.id
        ).all()
        if orphan_products:
            for p in orphan_products:
                p.shop_id = default_org.id
            db.commit()
            logger.info("Migrated %d products to default org", len(orphan_products))

        orphan_inventory = db.query(Inventory).filter(
            Inventory.shop_id != default_org.id
        ).all()
        if orphan_inventory:
            for inv in orphan_inventory:
                inv.shop_id = default_org.id
            db.commit()
            logger.info("Migrated %d inventory records to default org", len(orphan_inventory))

        orphan_sales = db.query(Sale).filter(
            Sale.shop_id != default_org.id
        ).all()
        if orphan_sales:
            for s in orphan_sales:
                s.shop_id = default_org.id
            db.commit()
            logger.info("Migrated %d sales to default org", len(orphan_sales))

    finally:
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
# Explicit re-import as per the requested configuration pattern
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://mme-project.vercel.app",
        "https://mme-project-p1qd0jd48-shivam-chourasias-projects.vercel.app"
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
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

from routers import orders
app.include_router(orders.router, prefix="/api/v1")

from routers import chat
app.include_router(chat.router, prefix="/api/v1")

try:
    from routers import auth_routes
    app.include_router(auth_routes.router, prefix="/api/v1")
    logger.info("✅ Auth routes registered: /api/v1/auth/*")
except Exception as e:
    logger.error("🚨 CRITICAL: Failed to load auth_routes: %s", str(e))
    import traceback
    traceback.print_exc()

from routers import public
app.include_router(public.router, prefix="/api/v1")
logger.info("✅ Public routes registered: /api/v1/public/*")

from routers import pricing
app.include_router(pricing.router, prefix="/api/v1")
logger.info("✅ Pricing routes registered: /api/v1/pricing/*")

from routers import tickets
app.include_router(tickets.router, prefix="/api/v1")
logger.info("✅ Ticket routes registered: /api/v1/tickets/*")

# ---------------- HEALTH CHECK ----------------
@app.get("/health")
def health_check():
    return {"status": "ok"}