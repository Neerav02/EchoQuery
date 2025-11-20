from sqlalchemy import Column, Integer, String
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    storage_name = Column(String)
    status = Column(String, default="PENDING")
    transcript = Column(String, nullable=True)
    
    # --- NEW FIELDS FOR THE BRAIN ---
    summary = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)