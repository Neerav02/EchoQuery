import pytest
import os
import json
import time
from fastapi.testclient import TestClient

from main import app
from events import publish_job_event, fetch_stream_history
from email_service import generate_executive_email_html, send_job_completion_email

# ==========================================
# 1. Real-Time Event & Stream Persistence Tests
# ==========================================

def test_publish_job_event_and_stream_history():
    job_id = 901
    
    # 1. Publish JOB_STATUS
    id1 = publish_job_event(job_id, "JOB_STATUS", {"status": "PROCESSING"})
    assert id1 is not None

    # 2. Publish TRANSCRIPT_SEGMENT
    id2 = publish_job_event(job_id, "TRANSCRIPT_SEGMENT", {
        "start_sec": 0.0,
        "end_sec": 3.5,
        "text": "Speech recognized on worker."
    })
    assert id2 is not None

    # 3. Publish SUMMARY_DELTA
    id3 = publish_job_event(job_id, "SUMMARY_DELTA", {
        "summary": "Executive summary text delta."
    })
    assert id3 is not None

    # Query full stream history
    history = fetch_stream_history(job_id)
    assert len(history) >= 3
    event_types = [h["event_type"] for h in history]
    assert "JOB_STATUS" in event_types
    assert "TRANSCRIPT_SEGMENT" in event_types
    assert "SUMMARY_DELTA" in event_types

def test_stream_reconnect_catch_up():
    job_id = 902

    # Emit initial event
    first_id = publish_job_event(job_id, "JOB_STATUS", {"status": "PENDING"})

    # Emit subsequent events
    publish_job_event(job_id, "TRANSCRIPT_SEGMENT", {"start_sec": 0.0, "end_sec": 2.0, "text": "Part 1"})
    publish_job_event(job_id, "TRANSCRIPT_SEGMENT", {"start_sec": 2.0, "end_sec": 4.0, "text": "Part 2"})
    publish_job_event(job_id, "JOB_STATUS", {"status": "COMPLETED"})

    # Client reconnects asking for events after first_id
    replayed = fetch_stream_history(job_id, last_event_id=first_id)
    assert len(replayed) == 3
    assert replayed[0]["data"]["text"] == "Part 1"
    assert replayed[1]["data"]["text"] == "Part 2"
    assert replayed[2]["data"]["status"] == "COMPLETED"

# ==========================================
# 2. WebSocket Stream Endpoint Tests
# ==========================================

def test_websocket_stream_receives_events():
    job_id = 903
    publish_job_event(job_id, "TRANSCRIPT_SEGMENT", {"start_sec": 0.0, "end_sec": 5.0, "text": "Stream segment test."})

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/stream/{job_id}") as ws:
            first_msg = ws.receive_json()
            assert "event_type" in first_msg or "data" in first_msg

# ==========================================
# 3. Email Notification Service Tests
# ==========================================

def test_email_service_html_generation():
    html = generate_executive_email_html(
        job_id=42,
        filename="system_presentation.mp4",
        transcript="Complete audio speech transcription text.",
        summary="Brief executive overview.",
        sentiment="POSITIVE",
        exec_time_ms=842.5
    )
    assert "#42" in html
    assert "system_presentation.mp4" in html
    assert "Complete audio speech transcription text." in html
    assert "Brief executive overview." in html
    assert "842.5ms" in html
    assert "EchoQuery" in html

def test_email_service_dispatch():
    success = send_job_completion_email(
        user_email="executive@company.com",
        job_id=42,
        filename="system_presentation.mp4",
        transcript="Sample transcript",
        summary="Sample summary",
        sentiment="POSITIVE",
        exec_time_ms=750.0
    )
    assert success is True

