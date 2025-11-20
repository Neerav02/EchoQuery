from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. The Connection String
# Format: postgresql://user:password@address:port/dbname
# Note: The address is "db" because that is the name we gave it in docker-compose!
SQLALCHEMY_DATABASE_URL = "postgresql://echo_user:echo_password@db:5432/echo_db"

# 2. Create the "Engine" (The connection manager)
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 3. Create the "Session" (The actual conversation window)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Base Class (All our tables will inherit from this)
Base = declarative_base()

# 5. A helper function to get the database session
# This opens a connection, lets us do work, and closes it automatically.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()