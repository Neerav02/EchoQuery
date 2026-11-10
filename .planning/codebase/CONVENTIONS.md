---
last_mapped_commit: 942e218d38ade9af39f40330c4ffa8f1f3d09a60
---

# Coding Conventions

**Analysis Date:** 2026-11-10

## Naming Patterns

**Files:**
- `snake_case.py` for all Python modules (`app/celery_app.py`, `app/redis_lock.py`, `app/email_service.py`).
- `test_*.py` for test modules (`app/tests/test_main.py`).
- `kebab-case.yaml` for Kubernetes and cloud infrastructure files (`k8s/apps-hpa.yaml`, `render.yaml`).

**Classes & Models:**
- `PascalCase` for SQLAlchemy database entities (`User`, `Job` in `app/models.py`).
- `PascalCase` for Pydantic schemas (`UserCreate`, `UserResponse` in `app/main.py`).
- `PascalCase` for internal utility classes (`ConnectionManager` in `app/main.py`).

**Functions & Endpoints:**
- `snake_case` for all functions and FastAPI route handlers (`read_root`, `create_user`, `upload_file`, `get_job_status`, `simulate_dlq_failure`, `replay_dlq`).
- `snake_case` for Celery task names (`create_task`, `replay_dlq_task`).
- `snake_case` for context managers and dependency injectors (`distributed_lock`, `get_db`, `get_redis_client`).

**Variables & Constants:**
- `snake_case` for local variables, request parameters, and model attributes (`job_id`, `user_email`, `exec_time_ms`, `lock_acquired`).
- `UPPER_SNAKE_CASE` for global configuration settings and environment variable lookups (`DATABASE_URL`, `REDIS_URL`, `BROKER_URL`, `RESULT_BACKEND`, `API_URL`).
- `_prefix` for internal singletons (`_redis_client` in `app/redis_lock.py`).

## Code Style & Organization

**Formatting:**
- Standard Python PEP 8 conventions: 4 spaces per indentation level, no tabs.
- Double quotes used predominantly for docstrings, multi-line strings, and log messages; single quotes frequently for dictionary keys and string literals.
- Module-level path resolution: Modules within `app/` include `sys.path.append(os.path.dirname(os.path.abspath(__file__)))` to enable flat sibling imports (`import models`, `from database import get_db`).

**Type Annotations:**
- Type hints used across FastAPI request bodies, responses, and dependency functions:
  ```python
  def execute_job_compute_logic(job_id: int, user_email: str = None) -> str: ...
  def get_job_status(job_id: int, db: Session = Depends(get_db)): ...
  ```
- Pydantic models configure ORM mapping using `ConfigDict(from_attributes=True)`:
  ```python
  class UserResponse(BaseModel):
      id: int
      email: str
      model_config = ConfigDict(from_attributes=True)
  ```

**Logging:**
- Standard library `logging` initialized per module using hierarchical namespacing:
  ```python
  logger = logging.getLogger("echoquery.api")     # in app/main.py
  logger = logging.getLogger("echoquery.tasks")   # in app/tasks.py
  logger = logging.getLogger("echoquery.redis")   # in app/redis_lock.py
  logger = logging.getLogger("echoquery.celery")  # in app/celery_app.py
  logger = logging.getLogger("echoquery.email")   # in app/email_service.py
  ```

## Import Organization

**Order:**
1. Standard library (`sys`, `os`, `uuid`, `logging`, `asyncio`, `time`, `socket`, `datetime`, `contextlib`).
2. Third-party dependencies (`fastapi`, `pydantic`, `sqlalchemy`, `celery`, `redis`, `kombu`, `boto3`, `streamlit`, `requests`).
3. Local application modules (`models`, `database`, `tasks`, `redis_lock`, `email_service`).

## Error Handling & Resilience Patterns

**FastAPI HTTP Exceptions:**
- Semantic HTTP status codes with explicit error details:
  - `400`: Duplicate registration or invalid client state (`Email already registered`).
  - `404`: Resource not found (`Job not found`).
  - `429`: Concurrency conflict (`Concurrent registration lock active. Please try again.`).
  - `500`: Internal dispatch or execution error.

**Defensive Fallback Pattern (Graceful Degradation):**
- External infrastructure is designed to degrade safely without crashing the service:
  - If Redis is unreachable, `distributed_lock` logs a warning and yields `True` (allowing standalone development and CI testing to pass).
  - If RabbitMQ broker port 5672 is not open, `is_broker_available()` returns `False`, and FastAPI processes the job locally using `BackgroundTasks`.
  - If PostgreSQL is not configured, `DATABASE_URL` defaults to `sqlite:///./echo_local.db`.

**Transaction Lifecycle Pattern:**
- Database sessions strictly managed via `try / except / finally`:
  ```python
  db = SessionLocal()
  try:
      # business logic
      db.commit()
  except Exception as e:
      db.rollback()
      raise
  finally:
      db.close()
  ```

---

*Conventions analysis: 2026-11-10*

