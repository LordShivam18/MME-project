import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. Fetch from Environment OR fallback to local SQLite
RAW_DB_URL = os.environ.get("DATABASE_URL", "sqlite:///./inventory_dev.db")

# 2. Render specifically provisions DBs as `postgres://` which breaks newer SQLAlchemy.
# We must intercept it and force standard dialect.
if RAW_DB_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DB_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DB_URL

# For SQLite, we must set check_same_thread for FastAPI multi-threading.
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
