---
last_mapped_commit: 942e218d38ade9af39f40330c4ffa8f1f3d09a60
---

# External Integrations

**Analysis Date:** 2026-11-10

## APIs & External Services

**Message Broker (RabbitMQ):**
- Purpose: Distributed task delivery, worker queue management, and fault-tolerant routing.
  - Client / Protocol: Kombu / AMQP via Celery (`amqp://guest:guest@broker:5672//` in Docker, `amqp://guest:guest@localhost:5672//` default).
  - Exchange & Queues: Direct exchange `echoquery_exchange` with queue `tasks` (routing key `task.process`).
  - Dead Letter Queue (DLQ): Dead letter exchange `echoquery_dlx` routing to queue `dlq` with routing key `task.dlq` configured via queue arguments `x-dead-letter-exchange` and `x-dead-letter-routing-key`.
  - Management UI: Exposed on port 15672 (`http://localhost:15672`).
  - Fallback / Detection: `app/main.py` performs a TCP socket probe on port 5672 (`is_broker_available()`); if RabbitMQ is not reachable, FastAPI seamlessly runs compute tasks locally via `BackgroundTasks`.

**Object Storage (MinIO / AWS S3):**
- Purpose: Durable cloud/local object storage for uploaded audio and video media files.
  - SDK / Client: `boto3` S3 client.
  - Connection Config: `S3_ENDPOINT_URL` (default `http://minio:9000`), `S3_BUCKET_NAME` (`echo-bucket`).
  - Auth: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
  - Container: `minio/minio` running in Docker Compose on ports 9000 (API) and 9001 (Console).

**Email Dispatch Service:**
- Purpose: Formats and dispatches responsive executive summaries and sentiment analytics reports upon task completion.
  - Implementation: `app/email_service.py` provides `generate_executive_email_html()` and `send_job_completion_email()`.
  - Report Structure: Dark-mode HTML email template including job reference, compute latency, queue delay, sentiment score badge, AI summary, and full transcription.
  - Status: Currently operates in logger-dispatch simulation mode ready for SMTP / SendGrid / SES adapter integration.

## Data Storage

**Relational Database (PostgreSQL & SQLite):**
- Primary (Production / Container): PostgreSQL 15 (`postgres:15-alpine` in Docker Compose, port 5432).
  - Connection: `DATABASE_URL` environment variable (`postgresql://echo_user:echo_password@db:5432/echo_db`).
  - Client / ORM: SQLAlchemy declarative models (`app/database.py`, `app/models.py`) with `psycopg2-binary`.
- Fallback (Development & Testing): SQLite local database (`echo_local.db`) or in-memory (`sqlite:///:memory:`).
  - Configured with `check_same_thread: False` and `StaticPool` for memory tests in `app/database.py` and `app/tests/test_main.py`.
- Schema Migration / Initialization:
  - Auto-created at startup via `models.Base.metadata.create_all(bind=engine)` inside the FastAPI lifespan handler in `app/main.py`.

**Distributed Cache & Locking (Redis):**
- Purpose: Distributed lock synchronization (preventing race conditions and concurrent writes across worker replicas) and Celery result backend.
  - Connection: `REDIS_URL` (`redis://localhost:6379/0`), Celery backend (`redis://localhost:6379/1`).
  - Client: `redis-py` (`redis.Redis.from_url(...)`) in `app/redis_lock.py` and Celery backend in `app/celery_app.py`.
  - Resilience: Automatic fallback if Redis is unavailable — `get_redis_client()` logs a warning and yields a non-blocking dummy lock; Celery falls back to `rpc://` backend.

## Internal Service Communication

**FastAPI Gateway ↔ Streamlit Frontend:**
- Frontend calls API over HTTP REST (`requests.get`, `requests.post`) using configurable `API_URL` (`frontend/main.py`).
- Key integrated routes:
  - `GET /system/stats` — Live system metrics (uptime, latency cut, worker speeds, DLQ count).
  - `POST /upload/` — Multipart media upload with optional recipient email.
  - `GET /jobs/{job_id}` — Polling task status, transcript, summary, and sentiment.
  - `GET /dlq/jobs` & `POST /dlq/replay/{job_id}` — DLQ monitoring and single-click task replay.
  - `POST /dlq/simulate-failure` — DLQ testing and error injection.
- WebSocket Streaming:
  - Route: `/ws/stream/{job_id}` via FastAPI WebSocket connection manager (`ConnectionManager` in `app/main.py`).

## CI/CD & Deployment Integrations

**GitHub Actions:**
- Workflow: `.github/workflows/main.yml`.
- Triggers on push and pull request to `main`.
- Environment: Ubuntu-latest, Python 3.10, in-memory SQLite, mocked AI and Celery dependencies.
- Executes `pytest -v` inside `app/`.

**PaaS Blueprints:**
- Render: `render.yaml` defines a web service (`echoquery`) combining FastAPI (`uvicorn app.main:app --port 8000`) and Streamlit (`streamlit run frontend/main.py --server.port $PORT --server.address 0.0.0.0`). Live URL: `https://echoquery.onrender.com`.
- Universal PaaS: `Procfile` defining `web`, `worker`, and `frontend` processes.

**Kubernetes Orchestration:**
- Manifests in `k8s/`:
  - `k8s/apps-hpa.yaml`: Deployments and Horizontal Pod Autoscalers (HPA) for `echoquery-api` and `echoquery-worker` (scaling 2 to 10 replicas based on CPU/memory thresholds).
  - `k8s/infrastructure.yaml`: StatefulSet / Deployments for PostgreSQL, Redis, and RabbitMQ with PersistentVolumeClaims.
  - `k8s/config.yaml`: Central `echoquery-config` ConfigMap.

---

*Integration analysis: 2026-11-10*

