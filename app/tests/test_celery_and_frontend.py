import os
import sys
import subprocess
from unittest.mock import MagicMock

from streamlit.testing.v1 import AppTest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = os.path.join(REPO_ROOT, "app")


def test_celery_task_registration_windows_host_layout():
    """Verify -A app.celery_app registers both tasks and uses a single Celery instance."""
    code = (
        "from app.celery_app import celery_app; "
        "celery_app.loader.import_default_modules(); "
        "import app.tasks; "
        "assert celery_app is app.tasks.celery_app, 'Split Celery instances detected'; "
        "tasks = sorted(n for n in celery_app.tasks if not n.startswith('celery.')); "
        "assert tasks == ['create_task', 'replay_dlq_task'], f'Unexpected tasks: {tasks}'"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"


def test_celery_task_registration_docker_layout():
    """Verify -A tasks.celery_app inside /app registers both tasks with single instance."""
    code = (
        "import sys; "
        f"sys.path.insert(0, {APP_DIR!r}); "
        "import tasks; "
        "ca = tasks.celery_app; "
        "ca.loader.import_default_modules(); "
        "import celery_app; "
        "assert ca is celery_app.celery_app, 'Split Celery instances in container'; "
        "reg = sorted(n for n in ca.tasks if not n.startswith('celery.')); "
        "assert reg == ['create_task', 'replay_dlq_task'], f'Unexpected tasks: {reg}'"
    )
    # Run from a neutral directory without parent `app` package in cwd
    neutral_dir = os.path.join(REPO_ROOT, "test_data")
    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=neutral_dir,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"


def test_is_broker_available_resolves_effective_broker_url(mocker):
    """Verify is_broker_available inspects resolved BROKER_URL rather than failing on Docker DNS."""
    import main

    mock_socket = MagicMock()
    mocker.patch("main.socket.socket", return_value=mock_socket)
    res = main.is_broker_available()
    assert res is True
    assert mock_socket.connect.called


def test_streamlit_frontend_renders_and_authenticates(mocker):
    """Verify Streamlit frontend boots cleanly without set_page_config errors and supports login."""
    def fake_get(url, **kwargs):
        resp = MagicMock()
        if url.endswith("/system/stats"):
            resp.status_code = 200
            resp.json.return_value = {
                "system_status": "99.99%",
                "api_latency_reduction": "40%",
                "avg_worker_execution_ms": 120.5,
                "total_tasks_processed": 3,
                "dead_letter_queue_count": 0,
            }
        elif url.endswith("/dlq/jobs"):
            headers = kwargs.get("headers") or {}
            if "Authorization" in headers:
                resp.status_code = 200
                resp.json.return_value = []
            else:
                resp.status_code = 401
                resp.json.return_value = {"detail": "Unauthorized"}
        return resp

    def fake_post(url, **kwargs):
        resp = MagicMock()
        if url.endswith("/auth/token"):
            resp.status_code = 200
            resp.json.return_value = {"access_token": "fake-jwt-token"}
        elif url.endswith("/auth/logout"):
            resp.status_code = 200
        return resp

    mocker.patch("requests.get", side_effect=fake_get)
    mocker.patch("requests.post", side_effect=fake_post)

    frontend_path = os.path.join(REPO_ROOT, "frontend", "main.py")
    at = AppTest.from_file(frontend_path)
    at.run(timeout=10)
    assert not at.exception
    assert not at.error

    # Test login interaction
    email_inp = [t for t in at.sidebar.text_input if t.label == "Email"][0]
    pass_inp = [t for t in at.sidebar.text_input if t.label == "Password"][0]
    email_inp.set_value("admin@echoquery.io")
    pass_inp.set_value("TestPass123!")
    login_btn = [b for b in at.sidebar.button if "Login" in b.label][0]
    login_btn.click()
    at.run(timeout=10)

    assert not at.exception
    assert not at.error
    assert any("admin@echoquery.io" in s.value for s in at.sidebar.success)


def test_dlq_replay_endpoint_resets_and_completes_job():
    """Verify POST /dlq/replay/{job_id} validates state, resets DLQ flags, and completes job."""
    from fastapi.testclient import TestClient
    from database import SessionLocal
    from main import app
    from security import create_access_token, hash_password
    import models

    db = SessionLocal()
    admin = models.User(
        email="replay_admin@example.com",
        hashed_password=hash_password("AdminPass123!"),
        is_superuser=True,
        password_migrated=True,
    )
    db.add(admin)
    dlq_job = models.Job(
        filename="failed_clip.wav",
        storage_name="failed-clip-key",
        status="DEAD_LETTER",
        is_dlq=True,
        retry_count=3,
        error_message="Simulated max retries exceeded",
    )
    normal_job = models.Job(
        filename="ok_clip.wav",
        storage_name="ok-clip-key",
        status="COMPLETED",
        is_dlq=False,
    )
    db.add_all([dlq_job, normal_job])
    db.commit()
    admin_id = admin.id
    dlq_id = dlq_job.id
    normal_id = normal_job.id
    db.close()

    token, _ = create_access_token({"sub": str(admin_id), "email": "replay_admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        # 404 on unknown job
        r_404 = client.post("/dlq/replay/999999", headers=headers)
        assert r_404.status_code == 404

        # 400 on non-DLQ job
        r_400 = client.post(f"/dlq/replay/{normal_id}", headers=headers)
        assert r_400.status_code == 400

        # 200 on DLQ job -> background task runs execute_job_compute_logic and completes it
        r_ok = client.post(f"/dlq/replay/{dlq_id}", headers=headers)
        assert r_ok.status_code == 200

    db = SessionLocal()
    updated = db.query(models.Job).filter(models.Job.id == dlq_id).first()
    assert updated.is_dlq is False
    assert updated.retry_count == 0
    assert updated.status == "COMPLETED"
    assert updated.error_message is None
    db.close()


def test_celery_create_task_retry_and_exhaustion_logic():
    """Verify real Celery create_task invokes self.retry before max_retries and diverts to DLQ when exhausted."""
    code = "\n".join([
        "import os, sys",
        "os.environ['ENVIRONMENT'] = 'test'",
        "os.environ['DATABASE_URL'] = 'sqlite:///:memory:'",
        f"sys.path.insert(0, {APP_DIR!r})",
        "from unittest.mock import patch",
        "from database import Base, engine, SessionLocal",
        "import models, tasks",
        "Base.metadata.create_all(bind=engine)",
        "db = SessionLocal()",
        "job = models.Job(filename='fail.wav', storage_name='fail.wav', status='PENDING', retry_count=0, max_retries=2)",
        "db.add(job)",
        "db.commit()",
        "job_id = job.id",
        "db.close()",
        "with patch('tasks.analyze_media_content', side_effect=RuntimeError('transient err')):",
        "    from celery.exceptions import Retry",
        "    with patch.object(tasks.create_task, 'retry', side_effect=Retry('celery_retry_triggered', RuntimeError('transient err'))) as mock_retry:",
        "        try:",
        "            tasks.create_task.apply(args=(job_id,), throw=True)",
        "            assert False, 'Expected retry trigger on attempt 1'",
        "        except Retry as exc:",
        "            assert 'celery_retry_triggered' in str(exc), str(exc)",
        "        assert mock_retry.call_count == 1",
        "db = SessionLocal()",
        "j1 = db.query(models.Job).filter(models.Job.id == job_id).first()",
        "assert j1.retry_count == 1 and j1.status == 'PENDING' and j1.is_dlq is False, (j1.retry_count, j1.status, j1.is_dlq)",
        "db.close()",
        "with patch('tasks.analyze_media_content', side_effect=RuntimeError('permanent err')):",
        "    res = tasks.create_task.apply(args=(job_id,)).get()",
        "    assert res == 'Failed'",
        "db = SessionLocal()",
        "j2 = db.query(models.Job).filter(models.Job.id == job_id).first()",
        "assert j2.retry_count == 2 and j2.status == 'DEAD_LETTER' and j2.is_dlq is True, (j2.retry_count, j2.status, j2.is_dlq)",
        "db.close()",
    ])
    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"


def test_streamlit_error_handling_and_dlq_controls(mocker):
    """Verify Streamlit handles invalid auth and failed DLQ replay without swallowing errors."""
    def fake_get(url, **kwargs):
        resp = MagicMock()
        if url.endswith("/system/stats"):
            resp.status_code = 200
            resp.json.return_value = {
                "system_status": "99.99%",
                "api_latency_reduction": "40%",
                "avg_worker_execution_ms": 50.0,
                "total_tasks_processed": 1,
                "dead_letter_queue_count": 1,
            }
        elif url.endswith("/dlq/jobs"):
            resp.status_code = 200
            resp.json.return_value = [
                {
                    "job_id": 99,
                    "filename": "broken.wav",
                    "error_message": "Simulated error",
                    "retry_count": 3,
                }
            ]
        return resp

    def fake_post(url, **kwargs):
        resp = MagicMock()
        if url.endswith("/auth/token"):
            resp.status_code = 401
            resp.text = "Unauthorized"
        elif "/dlq/replay/" in url:
            resp.status_code = 403
            resp.text = "Forbidden"
        else:
            resp.status_code = 200
        return resp

    mocker.patch("requests.get", side_effect=fake_get)
    mocker.patch("requests.post", side_effect=fake_post)

    frontend_path = os.path.join(REPO_ROOT, "frontend", "main.py")
    at = AppTest.from_file(frontend_path)
    at.run(timeout=10)

    # Trigger bad login -> shows error
    login_btn = [b for b in at.sidebar.button if "Login" in b.label][0]
    login_btn.click()
    at.run(timeout=10)
    assert any("Invalid credentials" in e.value for e in at.sidebar.error)

    # Trigger DLQ replay failure -> shows error instead of fake success
    replay_btn = [b for b in at.button if "Replay & Self-Heal" in b.label][0]
    replay_btn.click()
    at.run(timeout=10)
    assert any("Replay failed (403)" in e.value for e in at.error)
