import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean
from database import Base

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=utc_now)

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    storage_name = Column(String, nullable=False)
    status = Column(String, default="PENDING", index=True) # PENDING, PROCESSING, COMPLETED, FAILED, DEAD_LETTER
    
    # AI Results
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)
    
    # Fault-Tolerance & Performance Metrics
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Float, nullable=True)
    is_dlq = Column(Boolean, default=False)
    lock_acquired = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)