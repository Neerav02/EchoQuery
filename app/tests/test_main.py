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
from database import Base, SessionLocal
import models
from security import hash_password, create_access_token

def test_root_endpoint():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "EchoQuery" in response.json()["engine"]

def test_create_user():
    with TestClient(app) as client:
        response = client.post(
            "/users/",
            json={"email": "test@example.com", "password": "password123"}
        )
        assert response.status_code == 200
        assert response.json()["email"] == "test@example.com"

def test_create_duplicate_user():
    with TestClient(app) as client:
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
    mocker.patch('main.upload_file_stream')

    with TestClient(app) as client:
        # Create user & auth token
        reg_res = client.post("/users/", json={"email": "uploader@example.com", "password": "password123"})
        user_id = reg_res.json()["id"]
        token, _ = create_access_token({"sub": str(user_id), "email": "uploader@example.com"})

        files = {'file': ('test_audio.mp3', b'fake audio bytes', 'audio/mpeg')}
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/upload/", files=files, headers=headers)
        
        assert response.status_code == 200
        assert "job_id" in response.json()

def test_system_stats_endpoint():
    with TestClient(app) as client:
        response = client.get("/system/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["api_latency_reduction"] == "40%"
        assert "dead_letter_queue_count" in data

def test_dlq_workflow(mocker):
    mocker.patch('main.execute_job_compute_logic')

    db = SessionLocal()
    # Create superuser for DLQ administrative access
    admin = models.User(
        email="dlq_admin@example.com",
        hashed_password=hash_password("AdminPass123!"),
        is_superuser=True,
        password_migrated=True
    )
    db.add(admin)
    
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
    admin_id = admin.id
    db.close()

    token, _ = create_access_token({"sub": str(admin_id), "email": "dlq_admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        response = client.get("/dlq/jobs", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["job_id"] == job_id

        replay_res = client.post(f"/dlq/replay/{job_id}", headers=headers)
        assert replay_res.status_code == 200
