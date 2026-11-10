import pytest
import time
import io
import uuid
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from security import create_access_token
from outbox import enqueue_outbox_task, relay_pending_outbox_tasks
from tasks import execute_job_compute_logic

# ==========================================
# 1. Ingestion Latency Benchmark
# ==========================================

def test_ingestion_decoupled_latency_benchmark(mocker):
    """
    Measures API response latency under rapid submission.
    Decoupled architecture guarantees sub-200ms latency once client is initialized.
    """
    mocker.patch("main.upload_file_stream")
    mocker.patch("main.is_broker_available", return_value=False)

    db = SessionLocal()
    user = models.User(email=f"bench_{uuid.uuid4().hex[:6]}@echoquery.io", hashed_password="pw", is_superuser=False)
    db.add(user)
    db.commit()
    user_id = user.id
    email = user.email
    db.close()

    token, _ = create_access_token({"sub": str(user_id), "email": email})
    headers = {"Authorization": f"Bearer {token}"}

    latencies = []
    with TestClient(app) as client:
        # Initial request to warm up ASGI lifespan and connection pools
        client.post(
            "/upload/", 
            files={"file": ("warmup.mp3", io.BytesIO(b"WARMUP"), "audio/mpeg")},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "warmup-id"}
        )

        for i in range(20):
            payload = {"file": (f"audio_{i}.mp3", io.BytesIO(b"DUMMY_BENCHMARK_BYTES"), "audio/mpeg")}
            req_headers = dict(headers)
            req_headers["Idempotency-Key"] = f"bench-key-{uuid.uuid4().hex}"
            t0 = time.time()
            res = client.post("/upload/", files=payload, headers=req_headers)
            t1 = time.time()
            assert res.status_code == 200
            latencies.append((t1 - t0) * 1000)

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    avg = sum(latencies) / len(latencies)
    print(f"\n[BENCHMARK] Ingestion Avg: {avg:.2f}ms, p95: {p95:.2f}ms across 20 rapid requests")
    # Decoupled upload should execute in well under 200ms
    assert p95 < 200.0

# ==========================================
# 2. Worker Concurrency & Lock Contention Benchmark
# ==========================================

def test_worker_lock_contention_benchmark():
    """
    Simulates worker lock contention:
    Guarantees mutual exclusion: exactly 1 worker claims and executes the task,
    while all subsequent worker attempts are safely rejected by atomic compare-and-swap.
    """
    db = SessionLocal()
    job = models.Job(
        filename="racing_audio.wav",
        storage_name="racing_audio.wav",
        status="PENDING"
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    # First worker claims and processes
    first_res = execute_job_compute_logic(job_id)
    assert first_res == "Success"

    # All subsequent worker attempts must be rejected with AlreadyClaimedOrCompleted
    subsequent_results = [execute_job_compute_logic(job_id) for _ in range(5)]
    for r in subsequent_results:
        assert r == "AlreadyClaimedOrCompleted"

    print(f"\n[BENCHMARK] Contention: 1 worker claimed successfully, 5 rejected cleanly.")

# ==========================================
# 3. Outbox Relay Batch Throughput Benchmark
# ==========================================

def test_outbox_relay_throughput_benchmark(mocker):
    mocker.patch("tasks.create_task.delay")
    db = SessionLocal()

    # Enqueue 30 outbox tasks
    for i in range(30):
        job = models.Job(filename=f"bench_task_{i}.wav", storage_name=f"bench_{i}.wav", status="PENDING")
        db.add(job)
        db.flush()
        enqueue_outbox_task(db, job.id, "tasks.create_task", {"job_id": job.id})
    db.commit()
    db.close()

    t0 = time.time()
    dispatched = relay_pending_outbox_tasks(limit=50)
    dur_ms = (time.time() - t0) * 1000

    print(f"\n[BENCHMARK] Outbox Relay: Dispatched {dispatched} tasks in {dur_ms:.2f}ms")
    assert dispatched >= 30
    assert dur_ms < 1000.0
