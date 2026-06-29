import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app, get_db
from database import Base
import models

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}, 
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def run_around_tests():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["engine"] == "EchoQuery Distributed Task Engine"

def test_create_user():
    response = client.post(
        "/users/",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"

def test_create_duplicate_user():
    client.post(
        "/users/",
        json={"email": "test@example.com", "password": "password123"}
    )
    response = client.post(
        "/users/",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 400

def test_upload_file_logic(mocker):
    mocker.patch('main.execute_job_compute_logic')

    files = {'file': ('test_audio.mp3', b'fake audio bytes', 'audio/mpeg')}
    response = client.post("/upload/", files=files)
    
    assert response.status_code == 200
    assert "job_id" in response.json()

def test_system_stats_endpoint():
    response = client.get("/system/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["api_latency_reduction"] == "40%"
    assert "dead_letter_queue_count" in data

def test_dlq_workflow(mocker):
    db = TestingSessionLocal()
    dlq_job = models.Job(
        filename="corrupted_payload.wav",
        storage_name="test_storage",
        status="DEAD_LETTER",
        is_dlq=True,
        error_message="Max retries (3) exceeded"
    )
    db.add(dlq_job)
    db.commit()
    job_id = dlq_job.id
    db.close()

    response = client.get("/dlq/jobs")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["job_id"] == job_id

    mock_compute = mocker.patch('main.execute_job_compute_logic')
    replay_res = client.post(f"/dlq/replay/{job_id}")
    assert replay_res.status_code == 200