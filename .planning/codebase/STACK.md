---
last_mapped_commit: 942e218d38ade9af39f40330c4ffa8f1f3d09a60
---

# Technology Stack

**Analysis Date:** 2026-11-10

## Languages

**Primary:**
- Python 3.11+ — Core language for backend API (`app/`), worker services (`app/tasks.py`), and interactive UI (`frontend/main.py`).

**Secondary:**
- YAML / Shell / Dockerfile — Kubernetes manifests (`k8s/`), CI workflows (`.github/workflows/main.yml`), container definitions (`app/Dockerfile`, `frontend/Dockerfile`), and PaaS configurations (`render.yaml`, `Procfile`).

## Runtime

**Environment:**
- Python 3.11 (CPython) runtime running in Linux/containerized environments.
- Production multi-service Docker Alpine base (`postgres:15-alpine`, `redis:7-alpine`, `rabbitmq:3.12-management-alpine`).
- Compatible with Render PaaS native Python environment (pinned to `3.11.0` in `render.yaml`).

**Package Manager:**
- `pip` — Dependency management via `app/requirements.txt` and `frontend/requirements.txt`.
- No lockfile (`Pipfile.lock` or `poetry.lock`) currently present; versions are unpinned in `requirements.txt`.

## Frameworks

**Core:**
- FastAPI — Asynchronous REST API gateway, WebSocket streaming (`/ws/stream/{job_id}`), background task handling, and OpenAPI/Swagger documentation (`app/main.py`).
- Streamlit — Real-time interactive operator dashboard, DLQ replay console, and token streaming UI (`frontend/main.py`).
- Celery — Distributed task queue with custom exchange/queue routing and DLX policies (`app/celery_app.py`, `app/tasks.py`).
- SQLAlchemy — Declarative ORM and connection pooling abstraction supporting PostgreSQL and SQLite fallback (`app/database.py`, `app/models.py`).

**Testing:**
- Pytest — Test runner for backend test suite (`app/tests/test_main.py`).
- HTTPX (`TestClient`) — Synchronous/asynchronous ASGI test client for FastAPI endpoints.
- pytest-mock — Mocking library for unit and integration tests.

**Build / Dev / Server:**
- Uvicorn (`uvicorn[standard]`) — High-performance ASGI server for FastAPI.
- Gunicorn — WSGI HTTP production process manager.
- Docker Compose — Multi-container local development stack orchestration (`docker-compose.yml`).

## Key Dependencies

**Critical:**
- `fastapi` & `uvicorn[standard]` — REST & WebSocket API gateway and request routing (`app/main.py`).
- `celery` — Asynchronous background worker orchestration and retry backoff (`app/celery_app.py`, `app/tasks.py`).
- `sqlalchemy` — Database modeling and query execution (`app/database.py`, `app/models.py`).
- `psycopg2-binary` — PostgreSQL database adapter for production relational storage.
- `redis` — Distributed lock management via Redlock pattern and Celery result backend caching (`app/redis_lock.py`).
- `boto3` — AWS S3 / MinIO client for media file storage (`app/tasks.py`).
- `streamlit` — Frontend application framework (`frontend/main.py`).

**AI & Speech Intelligence (Optional / Simulated / Pluggable):**
- `openai-whisper` — Speech-to-text recognition model (`app/requirements.txt`).
- `transformers` & `torch` — Hugging Face NLP summarization and sentiment analysis pipelines (`app/requirements.txt`).

## Configuration

**Environment:**
- Environment variable configuration via `.env` and system environment variables (`os.getenv(...)`).
- Key environment variables:
  - `DATABASE_URL` — PostgreSQL connection string (`postgresql://...`) or SQLite fallback (`sqlite:///./echo_local.db`).
  - `REDIS_URL` — Redis connection URL for distributed locking (`redis://localhost:6379/0`).
  - `CELERY_BROKER_URL` — AMQP broker URL (`amqp://guest:guest@localhost:5672//`).
  - `CELERY_RESULT_BACKEND` — Redis or RPC backend (`redis://localhost:6379/1` or `rpc://`).
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL`, `S3_BUCKET_NAME` — MinIO/S3 object storage parameters.
  - `API_URL` — Gateway endpoint referenced by the Streamlit frontend (`http://localhost:8000`).

**Container & Deployment Config:**
- `docker-compose.yml` — Multi-container spec for 7 services (API, Worker, Redis, Frontend, DB, Broker, MinIO).
- `render.yaml` — Dual-process web service running FastAPI and Streamlit concurrently.
- `Procfile` — PaaS process declarations for `web`, `worker`, and `frontend`.
- `k8s/` — Kubernetes manifests for API gateway, workers, horizontal pod autoscalers (HPA), services, and config maps.

## Platform Requirements

**Development:**
- Cross-platform: Linux, macOS, or Windows (via WSL2 or native Python with local SQLite/Redis fallback).
- Optional local Docker & Docker Compose for full infrastructure (PostgreSQL, Redis, RabbitMQ, MinIO).

**Production:**
- Kubernetes cluster with metrics server for HPA (`k8s/apps-hpa.yaml`) or container-based PaaS (Render, Railway, Fly.io).

---

*Stack analysis: 2026-11-10*
*Update after major dependency changes*
