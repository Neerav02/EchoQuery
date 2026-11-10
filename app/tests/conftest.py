import os
import sys
from unittest.mock import MagicMock

# Force testing environment and in-memory database before any app module imports
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# 1. Fake the AI Libraries
sys.modules["whisper"] = MagicMock()
sys.modules["transformers"] = MagicMock()
sys.modules["torch"] = MagicMock()

# 2. Fake Celery
sys.modules["celery"] = MagicMock()
sys.modules["celery_app"] = MagicMock()

import pytest

# Ensure app directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine, Base, SessionLocal
from main import app
import models

@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
