---
last_mapped_commit: 942e218d38ade9af39f40330c4ffa8f1f3d09a60
---

# Codebase Structure

**Analysis Date:** 2026-11-10

## Directory Layout

```
echoquery/
├── .github/
│   └── workflows/
│       └── main.yml           # CI automated test workflow (GitHub Actions)
├── app/                       # Core backend API and worker service package
│   ├── tests/                 # Automated test suite
│   │   ├── __init__.py        # Test package marker
│   │   ├── conftest.py        # Test fixtures & dependency mocks (Whisper, Celery, Torch)
│   │   └── test_main.py       # API route & database integration tests
│   ├── celery_app.py          # Celery configuration, Kombu exchanges, DLQ queue definitions
│   ├── database.py            # SQLAlchemy engine configuration, pooling, get_db dependency
│   ├── Dockerfile             # Docker container definition for backend API & worker
│   ├── email_service.py       # Responsive dark-mode HTML executive report generator
│   ├── main.py                # FastAPI gateway entry point, REST endpoints, WebSocket manager
│   ├── models.py              # Relational database schemas (Job, User)
│   ├── redis_lock.py          # Redis Redlock distributed lock context manager
│   ├── requirements.txt       # Backend Python dependencies
│   └── tasks.py               # AI compute simulation, Celery task definitions, DLQ replay
├── frontend/                  # Presentation layer
│   ├── Dockerfile             # Docker container definition for Streamlit UI
│   ├── main.py                # Streamlit dashboard, metric cards, token streamer, DLQ console
│   └── requirements.txt       # Frontend Python dependencies
├── k8s/                       # Production Kubernetes manifests
│   ├── apps-hpa.yaml          # API/Worker deployments, LoadBalancer service, and HPAs
│   ├── config.yaml            # Central ConfigMap for cluster environment variables
│   └── infrastructure.yaml    # StatefulSet/Deployment manifests for DB, Redis, RabbitMQ
├── .dockerignore              # Exclusions for Docker image builds
├── .env                       # Local development environment configuration
├── .gitignore                 # Version control exclusion rules
├── docker-compose.yml         # 7-container local development stack orchestration
├── echo_local.db              # Local SQLite database file for rapid standalone development
├── Procfile                   # Process type declarations for PaaS (web, worker, frontend)
├── README.md                  # System architecture, benchmarks, API contracts, deployment guide
└── render.yaml                # Render infrastructure-as-code blueprint
```

## Directory Purposes

**`app/` (Backend Service Package):**
- Purpose: Contains the complete backend API gateway, asynchronous task workers, database ORM, locking mechanism, and notification logic.
- Key files:
  - `app/main.py`: Central FastAPI gateway with ASGI routes, WebSocket streaming handler, and lifespan management.
  - `app/tasks.py`: AI inference routines (`analyze_media_content`), compute dispatcher, and Celery tasks (`create_task`, `replay_dlq_task`).
  - `app/celery_app.py`: AMQP broker connection, Kombu dead-letter exchange topology.
  - `app/database.py`: Database connection engine supporting PostgreSQL and SQLite fallback.
  - `app/models.py`: SQLAlchemy schema definitions for `Job` and `User`.
  - `app/redis_lock.py`: Redis distributed locking context manager.
  - `app/email_service.py`: Automated HTML executive report formatting.

**`app/tests/` (Test Suite):**
- Purpose: Unit and integration testing for backend endpoints and async workflows.
- Key files:
  - `app/tests/conftest.py`: Mocks heavy dependencies (`whisper`, `transformers`, `torch`, `celery`) so tests run instantly without external infrastructure or GPU requirements.
  - `app/tests/test_main.py`: Test coverage for root endpoint, user registration, media uploads, system statistics, and DLQ replay workflows.

**`frontend/` (Streamlit Presentation Layer):**
- Purpose: Single-page administrative and operator dashboard.
- Key files:
  - `frontend/main.py`: Implements three tab views: AI Speech & Video Analyzer, Real-Time Token Streamer (WebSockets), and Dead Letter Queue (DLQ) Console.

**`k8s/` (Kubernetes Manifests):**
- Purpose: Production container orchestration on Kubernetes.
- Key files:
  - `k8s/apps-hpa.yaml`: Configures Horizontal Pod Autoscalers (HPA) targeting 2–10 replicas based on 70% CPU / 80% memory utilization.
  - `k8s/config.yaml`: Centralized ConfigMap (`echoquery-config`) defining connection URLs and S3 parameters.
  - `k8s/infrastructure.yaml`: In-cluster manifests for PostgreSQL, Redis, and RabbitMQ.

## Key File Locations

**Entry Points:**
- `app/main.py`: Backend ASGI API Gateway server (`uvicorn app.main:app`).
- `app/tasks.py`: Background Celery Worker process (`celery -A tasks.celery_app worker`).
- `frontend/main.py`: Streamlit Operator UI (`streamlit run frontend/main.py`).

**Configuration:**
- `docker-compose.yml`: Multi-container local orchestration.
- `render.yaml` & `Procfile`: PaaS cloud deployment configuration.
- `.env`: Local environment variable defaults.

**Core Logic:**
- `app/tasks.py`: Media analysis and compute pipeline (`execute_job_compute_logic`).
- `app/redis_lock.py`: Distributed concurrency control (`distributed_lock`).
- `app/models.py`: Entity definitions and state tracking.

**Testing:**
- `app/tests/test_main.py`: Integration test assertions using `fastapi.testclient.TestClient`.
- `app/tests/conftest.py`: Test environment fixtures and dependency mocks.

## Naming Conventions

**Files:**
- `snake_case.py` for Python modules (`celery_app.py`, `redis_lock.py`, `email_service.py`).
- `kebab-case.yaml` for Kubernetes and cloud config files (`apps-hpa.yaml`, `docker-compose.yml`).
- `test_*.py` for test files (`test_main.py`).

**Code Symbols:**
- `PascalCase` for SQLAlchemy models and Pydantic schemas (`User`, `Job`, `UserCreate`, `UserResponse`, `ConnectionManager`).
- `snake_case` for functions, endpoints, and variables (`create_task`, `execute_job_compute_logic`, `distributed_lock`, `get_db`).
- `UPPER_SNAKE_CASE` for global configuration constants (`DATABASE_URL`, `REDIS_URL`, `BROKER_URL`, `RESULT_BACKEND`).

---

*Structure analysis: 2026-11-10*

