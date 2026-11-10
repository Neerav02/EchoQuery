---
last_mapped_commit: 942e218d38ade9af39f40330c4ffa8f1f3d09a60
---

# Architecture

**Analysis Date:** 2026-11-10

## Pattern Overview

**Overall:** Decoupled Asynchronous Compute Gateway with Dual Execution Modes (Distributed Cluster & Embedded Async).

**Key Characteristics:**
- **Asynchronous Compute Decoupling:** Ingestion of heavy media/compute payloads is detached from synchronous HTTP request cycles; clients receive instant job acknowledgement (<50ms) to eliminate HTTP 504 timeouts.
- **Dual Execution Engine:**
  - *Distributed Cluster Mode:* Production Celery workers consume tasks from RabbitMQ with dead-letter exchange (DLX) routing and store status in PostgreSQL/Redis.
  - *Embedded Async Mode:* Local development or single-container environments fall back to FastAPI `BackgroundTasks` if RabbitMQ is offline.
- **Zero Write Conflict Guarantee:** Redis Redlock distributed locking pattern coordinates worker replicas to eliminate race conditions on shared job state.
- **Resilience & Self-Healing:** Exponential retry backoff with dedicated Dead Letter Queue (DLQ) isolation and interactive administrative replay console.

## Layers

**1. Presentation Layer (`frontend/main.py`):**
- Purpose: Operator dashboard for task dispatch, real-time WebSocket token streaming, system metric monitoring, and DLQ management.
- Contains: Streamlit application code, custom CSS styling, metric cards, tab navigation, and REST/WebSocket client handlers.
- Depends on: Gateway Layer (via HTTP requests and WebSockets).

**2. Gateway / Ingestion Layer (`app/main.py`):**
- Purpose: HTTP request routing, CORS configuration, WebSocket connection lifecycle management, and task dispatching.
- Contains: FastAPI router functions (`/`, `/health`, `/upload/`, `/jobs/{id}`, `/users/`, `/system/stats`, `/dlq/*`), `ConnectionManager`, lifespan startup/shutdown hooks.
- Depends on: Persistence Layer (`database.py`, `models.py`), Concurrency Layer (`redis_lock.py`), Compute Layer (`tasks.py`).

**3. Compute & Worker Layer (`app/tasks.py`, `app/celery_app.py`):**
- Purpose: Audio/video speech recognition simulation/inference (Whisper), NLP summarization (Transformers), and candidate sentiment evaluation.
- Contains: Celery task definitions (`create_task`, `replay_dlq_task`), `execute_job_compute_logic`, `analyze_media_content`, Kombu exchange/queue topology.
- Depends on: Concurrency Layer (`redis_lock.py`), Persistence Layer (`models.py`, `database.py`), Notification Layer (`email_service.py`).

**4. Concurrency & Synchronization Layer (`app/redis_lock.py`):**
- Purpose: Prevents concurrent worker collisions and race conditions during database writes and status transitions.
- Contains: `distributed_lock` context manager, `get_redis_client`, graceful mock-fallback for environments without Redis.
- Used by: Gateway Layer (user registration deduplication) and Compute Layer (job state transitions).

**5. Persistence & Modeling Layer (`app/database.py`, `app/models.py`):**
- Purpose: Relational data mapping and database connection pooling.
- Contains: SQLAlchemy `Base`, declarative models (`Job`, `User`), database engine initialization with SQLite/PostgreSQL URL parsing, `get_db` session dependency.
- Used by: Gateway Layer, Compute Layer, and Test Suites.

**6. Notification & Intelligence Layer (`app/email_service.py`):**
- Purpose: Formats and delivers enterprise HTML execution reports upon job completion.
- Contains: `generate_executive_email_html`, `send_job_completion_email`.
- Used by: Compute Layer.

## Data Flow

### 1. Media Upload & Asynchronous Ingestion Flow

```
[Client / Streamlit UI]
        │
        │ 1. POST /upload/ (multipart file + optional email)
        ▼
[FastAPI Gateway (app/main.py)]
        │
        ├─► 2. Save Job(status="PENDING") to DB (PostgreSQL / SQLite)
        │
        ├─► 3. Register background task (execute_job_compute_logic)
        │
        ├─► 4. If RabbitMQ available: create_task.delay(job_id, email)
        │
        ▼ 5. Return JSON {"message": "...", "job_id": 123} (<50ms)
[Client receives Job ID immediately]
```

### 2. Worker Execution & State Update Flow

```
[Worker (Celery or BackgroundTasks)]
        │
        ├─► 1. Acquire Redis lock: "job_process_{job_id}" (15s timeout)
        │
        ├─► 2. Update Job(status="PROCESSING", lock_acquired=True)
        │
        ├─► 3. Execute AI compute: Speech transcription & NLP summary
        │
        ├─► 4. Calculate execution_time_ms (<1200ms)
        │
        ├─► 5. Update Job(status="COMPLETED", transcript=..., summary=..., sentiment=...)
        │
        ├─► 6. Dispatch Executive HTML email report (if user_email provided)
        │
        └─► 7. Release Redis lock
```

### 3. Fault-Tolerance & Dead Letter Queue (DLQ) Replay Flow

```
[Task Failure / Payload Corruption]
        │
        ├─► 1. Automatic retry with exponential backoff (max_retries=3)
        │
        ├─► 2. If 3 retries exceeded: RabbitMQ routes to echoquery_dlx -> 'dlq' queue
        │      (or status set to "DEAD_LETTER", is_dlq=True in DB)
        │
        ├─► 3. Operator inspects failed payload in DLQ Console (frontend tab 3)
        │
        └─► 4. Operator clicks "Replay": POST /dlq/replay/{job_id} resets retries & re-executes
```

### 4. Real-Time Token Streaming Flow

```
[Client] ── WebSocket connect: /ws/stream/{job_id} ──► [FastAPI ConnectionManager]
                                                               │
[Client] ◄── Word-by-word token chunks emitted every 100ms ────┘
```

## State Management

- **Database State:** Persistent job metadata, transcripts, summaries, sentiment, retry counts, and execution metrics stored in PostgreSQL/SQLite.
- **In-Flight Task State:** RabbitMQ queues (`tasks`, `dlq`) track unacknowledged messages (`task_acks_late=True`, `task_reject_on_worker_lost=True`).
- **Distributed Lock State:** Transient keys `lock:job_process_{job_id}` in Redis with TTL safety timeouts.
- **WebSocket Connection State:** In-memory dictionary in `ConnectionManager` mapping `channel_id` to active WebSocket instances.

## Key Abstractions

**`distributed_lock` (`app/redis_lock.py`):**
- Python context manager that attempts to acquire a Redis lock. If Redis is unavailable, it gracefully logs a warning and yields `True`, allowing tests and single-container deployments to run uninterrupted.

**`ConnectionManager` (`app/main.py`):**
- Manages active client WebSockets for real-time streaming, segregating connections by `channel_id` and cleanly handling disconnects.

**`analyze_media_content` (`app/tasks.py`):**
- Pluggable AI inference boundary returning transcriptions, executive summaries, sentiment ratings, and skill tags based on uploaded filenames.

**`Job` Model (`app/models.py`):**
- Unified relational schema holding job lifecycle status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `DEAD_LETTER`), performance metrics (`execution_time_ms`), and fault-tolerance flags (`is_dlq`, `retry_count`, `lock_acquired`).

## Entry Points

- **API Gateway Entry Point:** `app/main.py` invoked via `uvicorn app.main:app --port 8000`.
- **Worker Process Entry Point:** `app/tasks.py` invoked via `celery -A tasks.celery_app worker --loglevel=info` (or `app.tasks.celery_app`).
- **Frontend Dashboard Entry Point:** `frontend/main.py` invoked via `streamlit run frontend/main.py`.
- **Combined Cloud Entry Point:** `Procfile` / `render.yaml` running FastAPI in background and Streamlit on port `$PORT`.

---

*Architecture analysis: 2026-11-10*
