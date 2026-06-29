import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# 1. Get Database URL from environment or default to local sqlite database for instant testing
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./echo_local.db"
)

# 2. Configure Engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}, 
        poolclass=StaticPool if ":memory:" in DATABASE_URL else None
    )
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()