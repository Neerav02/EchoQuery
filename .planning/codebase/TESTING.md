---
last_mapped_commit: 942e218d38ade9af39f40330c4ffa8f1f3d09a60
---

# Testing Patterns

**Analysis Date:** 2026-11-10

## Test Framework

**Runner:**
- Pytest (`pytest 7.x/8.x/9.x` with `pytest-mock` and `httpx`).
- Configured via CLI flags in GitHub Actions (`pytest -v`) and standard root directory discovery.

**Assertion Library:**
- Native Python `assert` statements.

**Run Commands:**
```bash
# Run full test suite from project root
pytest -v app/tests

# Run single test module
pytest -v app/tests/test_main.py

# Run a specific test function
pytest -v app/tests/test_main.py -k test_upload_file_logic
```

## Test File Organization

**Location:**
- Dedicated `tests/` directory inside `app/`:
```
app/
├── tests/
│   ├── __init__.py        # Test package marker
│   ├── conftest.py        # Global fixtures and sys.modules mocks
│   └── test_main.py       # API integration tests
```

**Naming:**
- Files: `test_*.py` (`test_main.py`).
- Functions: `test_<feature_or_endpoint_name>` (`test_root_endpoint`, `test_create_user`, `test_upload_file_logic`, `test_dlq_workflow`).

## Mocking & Dependency Isolation

**AI & Celery Module Mocks (`app/tests/conftest.py`):**
- In order to run fast headless unit and integration tests without downloading gigabytes of PyTorch weights or requiring a running RabbitMQ broker, `conftest.py` patches `sys.modules` before any test module is imported:
```python
import sys
from unittest.mock import MagicMock

# 1. Fake the AI Libraries
sys.modules["whisper"] = MagicMock()
sys.modules["transformers"] = MagicMock()
sys.modules["torch"] = MagicMock()

# 2. Fake Celery
sys.modules["celery"] = MagicMock()
sys.modules["celery_app"] = MagicMock()
```

**In-Memory Database Isolation:**
- Tests override the application database dependency using SQLite in-memory mode:
```python
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}, 
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
```

**Per-Test Schema Fixture:**
- An autouse fixture guarantees complete state isolation between test cases:
```python
@pytest.fixture(autouse=True)
def run_around_tests():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
```

## Test Structure & Patterns

**API Endpoint Testing Pattern (`fastapi.testclient.TestClient`):**
```python
client = TestClient(app)

def test_create_user():
    response = client.post(
        "/users/",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"
```

**Background Task Mocking Pattern (`pytest-mock`):**
```python
def test_upload_file_logic(mocker):
    # Mock compute execution to test gateway decoupling without delay
    mocker.patch('main.execute_job_compute_logic')

    files = {'file': ('test_audio.mp3', b'fake audio bytes', 'audio/mpeg')}
    response = client.post("/upload/", files=files)
    
    assert response.status_code == 200
    assert "job_id" in response.json()
```

## Current Test Coverage & Gaps

**Covered:**
- Root operational health check (`GET /`).
- User creation and duplicate conflict handling (`POST /users/`).
- Multipart file upload and asynchronous job dispatch (`POST /upload/`).
- System statistics aggregation (`GET /system/stats`).
- Dead Letter Queue inspection (`GET /dlq/jobs`) and job replay triggering (`POST /dlq/replay/{id}`).

**Coverage Gaps to Address:**
- **WebSocket Streaming:** `/ws/stream/{job_id}` currently lacks automated integration tests.
- **Frontend Dashboard:** `frontend/main.py` has no automated tests (e.g. via Playwright or Streamlit `AppTest`).
- **Distributed Lock Contention:** Edge cases where Redis lock is held by another worker replica.
- **Real Celery Task Lifecycle:** Task execution within a live Celery worker container.

---

*Testing analysis: 2026-11-10*

