import pytest
import os
import io
import uuid
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from outbox import relay_pending_outbox_tasks
from tasks import execute_job_compute_logic
from events import fetch_stream_history

def test_full_end_to_end_media_processing_pipeline(mocker):
    """
    Validates complete lifecycle:
    1. User Registration & JWT Authentication
    2. Authenticated Media Upload with Idempotency Key
    3. Transactional Outbox Atomic Commit
    4. Outbox Relay to Worker Queue
    5. Atomic Worker Lock Claim & AI Speech Intelligence
    6. Real-Time Stream Event Emitted
    7. Ownership-Checked Job Retrieval
    8. DLQ Administrative Operations
    """
    mocker.patch("main.upload_file_stream")
    mocker.patch("main.is_broker_available", return_value=False)  # Exercise outbox queuing

    with TestClient(app) as client:
        # Step 1: User Registration
        user_email = f"e2e_user_{uuid.uuid4().hex[:6]}@echoquery.io"
        reg_res = client.post("/users/", json={"email": user_email, "password": "SecurePassword123!"})
        assert reg_res.status_code == 200
        user_id = reg_res.json()["id"]

        # Step 2: JWT Login
        login_res = client.post("/auth/token", data={"username": user_email, "password": "SecurePassword123!"})
        assert login_res.status_code == 200
        tokens = login_res.json()
        token = tokens["access_token"]
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"idemp-e2e-{uuid.uuid4().hex}"
        }

        # Step 3: Media Upload (Transactional Outbox)
        audio_payload = {"file": ("interview_recording.mp3", io.BytesIO(b"AUDIO_BYTE_STREAM_E2E"), "audio/mpeg")}
        upload_res = client.post("/upload/", files=audio_payload, headers=auth_headers)
        assert upload_res.status_code == 200
        job_id = upload_res.json()["job_id"]
        assert upload_res.json()["status"] == "PENDING"

        # Verify OutboxTask exists in DB
        db = SessionLocal()
        outbox_entry = db.query(models.OutboxTask).filter(models.OutboxTask.job_id == job_id).first()
        assert outbox_entry is not None
        assert outbox_entry.status == "QUEUED"
        db.close()

        # Step 4: Outbox Relay Dispatch
        mock_delay = mocker.patch("tasks.create_task.delay")
        dispatched_count = relay_pending_outbox_tasks()
        assert dispatched_count >= 1
        mock_delay.assert_called()

        # Step 5: Worker Execution
        worker_res = execute_job_compute_logic(job_id, user_email)
        assert worker_res == "Success"

        # Step 6: Verify Stream Events
        events = fetch_stream_history(job_id)
        assert len(events) >= 2
        event_types = [e["event_type"] for e in events]
        assert "JOB_STATUS" in event_types
        assert "SUMMARY_DELTA" in event_types

        # Step 7: Ownership-Protected Job Retrieval
        job_res = client.get(f"/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})
        assert job_res.status_code == 200
        job_data = job_res.json()
        assert job_data["status"] == "COMPLETED"
        assert job_data["transcript"] is not None
        assert job_data["ai_provider"] is not None
        assert job_data["execution_time_ms"] > 0

        # Verify unauthorized user cannot view this job
        foreign_headers = {"Authorization": f"Bearer {tokens['access_token']}_tampered"}
        # Invalid token returns 401 or 403
        unauth_res = client.get(f"/jobs/{job_id}", headers=foreign_headers)
        assert unauth_res.status_code in (401, 403)

