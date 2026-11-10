import pytest
import uuid
import json
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from database import SessionLocal
import models
from main import app

# ==========================================
# 1. Request Correlation ID Tests
# ==========================================

def test_correlation_id_generated_automatically():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert "X-Request-ID" in res.headers
        corr_id = res.headers["X-Request-ID"]
        assert len(corr_id) >= 32

def test_correlation_id_propagated_from_client():
    custom_id = "trace-client-uuid-987654321"
    with TestClient(app) as client:
        res = client.get("/health", headers={"X-Request-ID": custom_id})
        assert res.status_code == 200
        assert res.headers.get("X-Request-ID") == custom_id

# ==========================================
# 2. Prometheus Metrics Endpoint Tests
# ==========================================

def test_prometheus_metrics_endpoint():
    db = SessionLocal()
    job = models.Job(
        filename="metrics_test.wav",
        storage_name="metrics_test.wav",
        status="COMPLETED",
        execution_time_ms=125.4
    )
    db.add(job)
    db.commit()
    db.close()

    with TestClient(app) as client:
        res = client.get("/metrics")
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        body = res.text
        assert "echoquery_tasks_total" in body
        assert 'echoquery_tasks_total{status="completed"}' in body
        assert "echoquery_worker_execution_time_ms_avg" in body

# ==========================================
# 3. Redis Stats Caching Tests
# ==========================================

def test_system_stats_redis_caching(mocker):
    fake_redis = MagicMock()
    cached_payload = {
        "system_status": "99.99% Operational",
        "total_tasks_processed": 500,
        "completed_tasks": 490,
        "failed_tasks": 5,
        "dead_letter_queue_count": 5,
        "api_latency_reduction": "40%",
        "avg_worker_execution_ms": 78.5,
        "distributed_lock_status": "ACTIVE (Redis Redlock)"
    }
    fake_redis.get.return_value = json.dumps(cached_payload)
    mocker.patch("main.get_redis_client", return_value=fake_redis)

    with TestClient(app) as client:
        res = client.get("/system/stats")
        assert res.status_code == 200
        data = res.json()
        assert data["total_tasks_processed"] == 500
        fake_redis.get.assert_called_once_with("cache:system_stats")
