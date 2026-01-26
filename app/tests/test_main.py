import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock
import sys
import os

# 1. Setup paths so Python finds 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app, get_db
from database import Base
import models

# 2. Setup Temporary Test Database (SQLite)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}, 
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. Override the dependency
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# 4. Create the Test Client
client = TestClient(app)

# 5. Setup/Teardown (Reset DB for each test)
@pytest.fixture(autouse=True)
def run_around_tests():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

# --- THE ACTUAL TESTS ---

def test_create_user():
    """Test if we can create a user successfully"""
    response = client.post(
        "/users/",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"

def test_create_duplicate_user():
    """Test that creating the same user twice fails"""
    # First creation
    client.post(
        "/users/",
        json={"email": "test@example.com", "password": "password123"}
    )
    # Second creation (Should fail)
    response = client.post(
        "/users/",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 400

def test_upload_file_logic(mocker):
    """
    Test file upload. 
    We MOCK the S3 and Celery parts so we don't need real AWS/RabbitMQ.
    """
    # Mock S3 upload
    mock_s3 = mocker.patch('main.s3_client.upload_fileobj')
    
    # Mock Celery Task
    mock_celery = mocker.patch('main.create_task.delay')

    # Fake file content
    files = {'file': ('test_audio.mp3', b'fake audio bytes', 'audio/mpeg')}
    
    response = client.post("/upload/", files=files)
    
    assert response.status_code == 200
    assert "job_id" in response.json()
    
    # Verify our mocks were called (proving the logic reached that point)
    mock_s3.assert_called_once()
    mock_celery.assert_called_once()