import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    password_migrated = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    
    jobs = relationship("Job", back_populates="owner")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    
    user = relationship("User", back_populates="refresh_tokens")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    filename = Column(String, nullable=False)
    storage_name = Column(String, nullable=False)
    storage_bucket = Column(String, default="echo-bucket", nullable=True)
    status = Column(String, default="PENDING", index=True) # PENDING, PROCESSING, COMPLETED, FAILED, DEAD_LETTER
    idempotency_key = Column(String(64), unique=True, nullable=True, index=True)
    lock_token = Column(String(64), nullable=True)
    
    # AI Results & Metrics
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)
    ai_provider = Column(String, nullable=True)
    ai_model = Column(String, nullable=True)
    token_usage = Column(Integer, nullable=True)
    
    # Fault-Tolerance & Performance Metrics
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Float, nullable=True)
    is_dlq = Column(Boolean, default=False)
    lock_acquired = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    
    owner = relationship("User", back_populates="jobs")

class OutboxTask(Base):
    __tablename__ = "outbox_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    topic = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String, default="QUEUED", index=True) # QUEUED, DISPATCHED, FAILED
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    dispatched_at = Column(DateTime, nullable=True)
