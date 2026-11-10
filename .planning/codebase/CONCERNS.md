---
last_mapped_commit: 942e218d38ade9af39f40330c4ffa8f1f3d09a60
---

# Codebase Concerns

**Analysis Date:** 2026-11-10

## Tech Debt

**1. Mocked / Simulated AI Inference Layer (`app/tasks.py`):**
- **Issue:** `analyze_media_content()` simulates Whisper speech-to-text recognition and Transformers NLP summarization using conditional string matching rather than executing deep neural models.
- **Why:** Full AI models require significant GPU/VRAM resources (1–4GB+) and heavy package downloads (`torch`, `transformers`, `openai-whisper`), which would make free-tier PaaS deployment (Render) and automated CI infeasible.
- **Impact:** System functions as an architectural demonstration and task orchestration engine rather than production-grade audio processing.
- **Fix approach:** Implement a unified strategy/adapter pattern with a `SpeechTranscriber` interface having two implementations: `SimulatedTranscriber` for dev/demo/CI, and `WhisperTranscriber` for production GPU workers.

**2. Dual Compute Execution in API Gateway (`app/main.py`):**
- **Issue:** In `POST /upload/`, the endpoint unconditionally queues `background_tasks.add_task(execute_job_compute_logic, ...)` AND conditionally triggers `create_task.delay(...)` if RabbitMQ is reachable:
  ```python
  background_tasks.add_task(execute_job_compute_logic, new_job.id, email)
  if is_broker_available():
      create_task.delay(new_job.id, email)
  ```
- **Why:** Implemented as a safety mechanism to guarantee tasks complete in local/hybrid environments even if Celery workers are offline.
- **Impact:** When both the broker and Celery workers are active, the task is executed twice concurrently. Redis locking prevents data corruption, but worker compute cycles are wasted.
- **Fix approach:** Only dispatch to `background_tasks` if `not is_broker_available()`.

**3. Unpinned Dependencies (`app/requirements.txt`, `frontend/requirements.txt`):**
- **Issue:** Dependencies (`fastapi`, `celery`, `sqlalchemy`, `streamlit`, `torch`) have no pinned versions or lockfiles (`Pipfile.lock` or `poetry.lock`).
- **Why:** Simplified rapid prototyping.
- **Impact:** Upstream major releases can break deployments or cause runtime incompatibilities (e.g., Python 3.13 compatibility nuances with Celery/Starlette).
- **Fix approach:** Adopt `pip-tools` (`requirements.in` / `requirements.txt`) or `poetry` to pin exact versions.

**4. `sys.path` Module Resolution Hack:**
- **Issue:** `sys.path.append(os.path.dirname(os.path.abspath(__file__)))` is used in `app/main.py`, `app/tasks.py`, and `app/tests/test_main.py`.
- **Why:** Allows flat imports (`import models`, `from database import engine`) when executing files directly.
- **Impact:** Causes ambiguity in IDEs, linter path errors, and brittle packaging.
- **Fix approach:** Structure `app` as an installable package with standard package-relative imports (`from app.database import engine`).

## Known Bugs & Fragile Areas

**1. TestClient Blocking Under Python 3.13 on Windows:**
- **Symptoms:** Running `pytest` on Windows using Python 3.13 hangs indefinitely during `client.get("/")` or `lifespan` execution.
- **Root cause:** Starlette's `TestClient` manages ASGI lifespan using background event loop threads via AnyIO, which encounters thread-blocking deadlocks under Python 3.13 on Windows unless explicitly run inside an active context manager (`with TestClient(app) as client:`).
- **Workaround:** CI specifically targets Python 3.10 (`.github/workflows/main.yml`), and Render pins Python 3.11.0 (`render.yaml`).
- **Fix approach:** Update `app/tests/test_main.py` to use `with TestClient(app) as client:` context managers or use `pytest-asyncio` with HTTPX `AsyncClient`.

**2. Single-Container Multi-Process Fragility (`render.yaml`, `Procfile`):**
- **Symptoms:** In Render's free tier, FastAPI and Streamlit run in a single container via shell backgrounding:
  ```bash
  uvicorn app.main:app --port 8000 & streamlit run frontend/main.py --server.port $PORT --server.address 0.0.0.0
  ```
- **Risk:** Shell backgrounding (`&`) does not provide process monitoring. If the Uvicorn process crashes, the container remains running because Streamlit is alive, resulting in silent 502/connection refused errors for all API calls.
- **Fix approach:** Use a lightweight process supervisor like `supervisord` or `honcho` in multi-process containers, or deploy frontend and backend as separate services.

## Security Considerations

**1. Plaintext Password Storage (`app/main.py`):**
- **Risk:** `models.User(email=user.email, hashed_password=user.password)` stores the user's password directly in the `hashed_password` column without hashing.
- **Current mitigation:** None; user registration is currently a demonstration feature.
- **Recommendation:** Implement `passlib` / `bcrypt` (`pwd_context.hash(user.password)`).

**2. Permissive CORS Policy (`app/main.py`):**
- **Risk:** `allow_origins=["*"]` combined with `allow_credentials=True` is an insecure configuration that allows any arbitrary site to make credentialed cross-origin requests.
- **Recommendation:** Restrict `allow_origins` to known frontend domains or environment-configured origin lists.

**3. Unauthenticated Administrative Endpoints:**
- **Risk:** Endpoints such as `/upload/`, `/dlq/jobs`, `/dlq/replay/{id}`, and `/system/stats` have no authentication or rate limiting. Any user can trigger job executions, simulate failures, or replay DLQ jobs.
- **Recommendation:** Add JWT or API Key authentication middleware to administrative and compute endpoints.

**4. Default Credentials in Compose Configuration:**
- **Risk:** Hardcoded default passwords in `docker-compose.yml` (`echo_password`, `minio_password`, `guest:guest`).
- **Recommendation:** Ensure production environments use secret management (e.g., Kubernetes Secrets, HashiCorp Vault) rather than default compose credentials.

## Performance Bottlenecks

**1. Synchronous Sleep Simulation in Worker (`app/tasks.py`):**
- **Problem:** `time.sleep(0.8)` is used to simulate compute processing.
- **Impact:** In the embedded `BackgroundTasks` mode, this blocks worker threads in the default FastAPI threadpool, reducing request throughput under load.
- **Improvement path:** In async mode, use `await asyncio.sleep(0.8)` or delegate strictly to Celery worker pools.

**2. Polling Metrics from Streamlit (`frontend/main.py`):**
- **Problem:** Streamlit re-executes the script on every user interaction, triggering `requests.get(f"{API_URL}/system/stats")` each time.
- **Impact:** Redundant queries to the database aggregating `Job.count()` and execution time averages.
- **Improvement path:** Cache stats in Streamlit using `@st.cache_data(ttl=5)` or cache results in Redis.

---

*Concerns analysis: 2026-11-10*
