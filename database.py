import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
import logging

logger = logging.getLogger(__name__)

# 1. Fetch from Environment (STRICTLY NO FALLBACK)
RAW_DB_URL = os.environ.get("DATABASE_URL")
if not RAW_DB_URL:
    raise ValueError("DATABASE_URL environment variable is required. No SQLite fallback allowed in production.")

# 2. Render specifically provisions DBs as `postgres://` which breaks newer SQLAlchemy.
# We must intercept it and force standard dialect.
if RAW_DB_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DB_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DB_URL

# 3. Supabase Pooler Validation (Render IPv4 constraint)
if "supabase" in DATABASE_URL and "5432" in DATABASE_URL:
    raise ValueError(
        "Direct Subabase connection (port 5432) detected! Render does not support direct IPv6 DB connections. "
        "You MUST use the Supabase Connection Pooler URL (typically port 6543)."
    )

# When using Supabase pooler (PgBouncer), we disable internal SQLAlchemy connection pooling 
# so they don't combat each other, preventing "Network is unreachable" proxy drops.
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
