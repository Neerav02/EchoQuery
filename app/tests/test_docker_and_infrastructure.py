import os
import re
import pytest
import yaml
from fastapi.testclient import TestClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = os.path.join(REPO_ROOT, "app")
FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")
COMPOSE_FILE = os.path.join(REPO_ROOT, "docker-compose.yml")

from main import app


def test_app_dockerfile_port_and_healthcheck_alignment():
    """Validates REQ-INFRA-01: app/Dockerfile aligns on port 8000 and /health endpoint."""
    dockerfile_path = os.path.join(APP_DIR, "Dockerfile")
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. EXPOSE 8000
    assert re.search(r"^EXPOSE\s+8000\b", content, re.MULTILINE), "app/Dockerfile must EXPOSE port 8000"

    # 2. HEALTHCHECK curls /health on port 8000
    assert re.search(
        r"HEALTHCHECK.*CMD\s+curl.*http://localhost:8000/health",
        content,
        re.DOTALL,
    ), "app/Dockerfile HEALTHCHECK must target http://localhost:8000/health"

    # 3. CMD binds uvicorn to 0.0.0.0:8000
    assert re.search(
        r'CMD\s*\[.*"uvicorn".*"--host",\s*"0.0.0.0",\s*"--port",\s*"8000".*\]',
        content,
    ), 'app/Dockerfile CMD must bind uvicorn to --port 8000'

    # Ensure no leftover active port 80 binding
    active_lines = "\n".join(line for line in content.splitlines() if not line.strip().startswith("#"))
    assert not re.search(
        r'"--port",\s*"80"', active_lines
    ), "app/Dockerfile must not contain active port 80 binding"


def test_frontend_dockerfile_healthcheck_and_port():
    """Validates Streamlit frontend Dockerfile configuration on port 8501."""
    dockerfile_path = os.path.join(FRONTEND_DIR, "Dockerfile")
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert re.search(r"^EXPOSE\s+8501\b", content, re.MULTILINE), "frontend/Dockerfile must EXPOSE port 8501"
    assert re.search(
        r"HEALTHCHECK.*CMD\s+curl.*http://localhost:8501/_stcore/health",
        content,
        re.DOTALL,
    ), "frontend/Dockerfile HEALTHCHECK must target http://localhost:8501/_stcore/health"


def test_docker_compose_configuration_and_dependencies():
    """Validates REQ-INFRA-01 & REQ-INFRA-02: Compose port mappings, healthcheck, and dependencies."""
    with open(COMPOSE_FILE, "r", encoding="utf-8") as f:
        compose_data = yaml.safe_load(f)

    services = compose_data.get("services", {})
    assert "api" in services, "Compose must define api service"
    assert "frontend" in services, "Compose must define frontend service"
    assert "worker" in services, "Compose must define worker service"
    assert "db" in services, "Compose must define db service"
    assert "redis" in services, "Compose must define redis service"
    assert "broker" in services, "Compose must define broker service"
    assert "minio" in services, "Compose must define minio (silo) service"

    # API configuration
    api = services["api"]
    assert "8000:8000" in api.get("ports", []), "api service must publish 8000:8000"
    api_health = api.get("healthcheck", {})
    assert api_health.get("test") == ["CMD", "curl", "-f", "http://localhost:8000/health"]

    # Frontend configuration
    frontend = services["frontend"]
    assert "8501:8501" in frontend.get("ports", []), "frontend service must publish 8501:8501"
    assert frontend.get("environment", {}).get("API_URL") == "http://api:8000", (
        "frontend API_URL must point to http://api:8000"
    )
    frontend_deps = frontend.get("depends_on", {})
    assert isinstance(frontend_deps, dict) and frontend_deps.get("api", {}).get("condition") == "service_healthy", (
        "frontend must depend on api being service_healthy"
    )

    # Worker configuration
    worker = services["worker"]
    worker_deps = worker.get("depends_on", {})
    assert "broker" in worker_deps and "redis" in worker_deps and "db" in worker_deps

    # Persistent volumes preserved
    volumes = compose_data.get("volumes", {})
    assert "postgres_data" in volumes
    assert "redis_data" in volumes
    assert "minio_data" in volumes


def test_api_health_endpoint_operational():
    """Validates that GET /health returns 200 with service health payload."""
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "healthy"
        assert data.get("service") == "echoquery-api"
        assert "timestamp" in data


def test_frontend_backend_api_url_contract():
    """Validates that frontend default API URL targets port 8000 and matches backend endpoints."""
    frontend_main = os.path.join(FRONTEND_DIR, "main.py")
    with open(frontend_main, "r", encoding="utf-8") as f:
        fe_code = f.read()

    # Verify fallback default is port 8000
    assert 'os.getenv("API_URL", "http://127.0.0.1:8000")' in fe_code

    # Verify backend satisfies all endpoints consumed by frontend
    with TestClient(app) as client:
        # 1. Root /
        r_root = client.get("/")
        assert r_root.status_code == 200
        assert "engine" in r_root.json()

        # 2. System stats /system/stats
        r_stats = client.get("/system/stats")
        assert r_stats.status_code == 200
        assert "system_status" in r_stats.json()
        assert "api_latency_reduction" in r_stats.json()

        # 3. Healthcheck /health
        r_health = client.get("/health")
        assert r_health.status_code == 200


def test_app_dockerfile_contains_ffmpeg_and_cpu_torch():
    """Validates that app/Dockerfile installs FFmpeg and references CPU-only PyTorch index."""
    dockerfile_path = os.path.join(APP_DIR, "Dockerfile")
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Active lines (ignoring commented headers)
    active = "\n".join(line for line in content.splitlines() if not line.strip().startswith("#"))

    assert re.search(r"apt-get\s+install.*ffmpeg", active, re.DOTALL), "app/Dockerfile must install ffmpeg"
    assert "https://download.pytorch.org/whl/cpu" in active, (
        "app/Dockerfile must use CPU-only PyTorch index to prevent downloading CUDA binaries"
    )


def test_docker_compose_prod_zero_host_port_leaks():
    """Validates that docker-compose.prod.yml exposes ONLY ports 80/443 on Caddy with ZERO internal port leaks."""
    prod_compose = os.path.join(REPO_ROOT, "docker-compose.prod.yml")
    assert os.path.exists(prod_compose), "docker-compose.prod.yml must exist"

    with open(prod_compose, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})

    # 1. Caddy publishes only 80 and 443
    assert "caddy" in services
    caddy_ports = services["caddy"].get("ports", [])
    assert "80:80" in caddy_ports
    assert "443:443" in caddy_ports
    assert len(caddy_ports) == 2, f"Caddy should only expose 80 and 443, found: {caddy_ports}"

    # 2. None of the internal services publish ports to the host
    for svc in ("api", "worker", "frontend", "db", "redis", "broker", "minio"):
        assert svc in services, f"Production Compose must define {svc}"
        assert "ports" not in services[svc], (
            f"Production service {svc} must NOT publish ports to host (security risk)"
        )

    # 3. All services must define restart: unless-stopped
    for name, svc in services.items():
        assert svc.get("restart") == "unless-stopped", f"Service {name} must have restart: unless-stopped"


def test_docker_compose_prod_no_dev_bind_mounts():
    """Validates that production services do not mount local developer source folders."""
    prod_compose = os.path.join(REPO_ROOT, "docker-compose.prod.yml")
    with open(prod_compose, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    for svc in ("api", "worker", "frontend"):
        volumes = services[svc].get("volumes", [])
        for v in volumes:
            assert "./app:/app" not in v and "./frontend:/app" not in v, (
                f"Production service {svc} must not bind mount source code"
            )


def test_docker_compose_prod_concurrency_one():
    """Validates that Celery worker concurrency is set to 1 for the 2 OCPU / 12 GB RAM budget."""
    prod_compose = os.path.join(REPO_ROOT, "docker-compose.prod.yml")
    with open(prod_compose, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    worker = data.get("services", {}).get("worker", {})
    command = worker.get("command", "")
    assert "--concurrency=1" in command, (
        f"Worker must run with --concurrency=1 for 2 OCPU / 12 GB RAM budget, got: {command}"
    )


def test_caddyfile_routing_and_domain_variable():
    """Validates that Caddyfile configures {$DOMAIN_NAME}, WebSockets, and API/UI routing."""
    caddyfile_path = os.path.join(REPO_ROOT, "Caddyfile")
    assert os.path.exists(caddyfile_path), "Caddyfile must exist"

    with open(caddyfile_path, "r", encoding="utf-8") as f:
        caddy_text = f.read()

    assert "{$DOMAIN_NAME}" in caddy_text, "Caddyfile must configure domain via {$DOMAIN_NAME}"
    assert "localhost" not in caddy_text.splitlines()[3], "Production Caddyfile domain block must not use hardcoded localhost"
    assert "/ws/*" in caddy_text, "Caddyfile must support FastAPI WebSocket route /ws/*"
    assert "api:8000" in caddy_text, "Caddyfile must reverse_proxy to api:8000"
    assert "frontend:8501" in caddy_text, "Caddyfile must reverse_proxy to frontend:8501"
    assert "86400s" in caddy_text, "Caddyfile must configure long timeouts for persistent streaming"


def test_production_demo_account_disabled(monkeypatch):
    """Validates that demo@echoquery.io registration is rejected with 403 in production."""
    from config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    with TestClient(app) as client:
        res = client.post("/users/", json={"email": "demo@echoquery.io", "password": "DemoPassword123!"})
        assert res.status_code == 403
        assert "disabled in production" in res.json().get("detail", "").lower()


def test_frontend_demo_login_toggle():
    """Validates that frontend/main.py enforces demo login visibility based on environment."""
    frontend_path = os.path.join(FRONTEND_DIR, "main.py")
    with open(frontend_path, "r", encoding="utf-8") as f:
        fe_code = f.read()

    assert "is_production = os.getenv(\"ENVIRONMENT\", \"\").strip().lower() == \"production\"" in fe_code
    assert "ENABLE_DEMO_LOGIN" in fe_code
    assert "allow_demo" in fe_code


def test_docker_compose_prod_mandatory_credentials_and_redis_auth():
    """Validates that docker-compose.prod.yml enforces mandatory secrets and Redis auth."""
    prod_compose = os.path.join(REPO_ROOT, "docker-compose.prod.yml")
    with open(prod_compose, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Mandatory variables with :? error guards
    for required_var in ("DOMAIN_NAME", "POSTGRES_PASSWORD", "REDIS_PASSWORD", "RABBITMQ_DEFAULT_PASS", "MINIO_ROOT_PASSWORD"):
        pattern = rf"\${{{required_var}:\?"
        assert re.search(pattern, content), f"docker-compose.prod.yml must guard {required_var} with :? mandatory check"

    # 2. Redis requirepass command and authenticated healthcheck
    assert re.search(r'redis-server\s+--requirepass', content), "Redis must enforce --requirepass"
    assert re.search(r'redis-cli\s+-a', content), "Redis healthcheck must authenticate with -a"

    # 3. API and Worker use authenticated Redis URLs
    assert "redis://:${REDIS_PASSWORD:-}@redis:6379/0" in content
    assert "redis://:${REDIS_PASSWORD:-}@redis:6379/1" in content


def test_caddyfile_enforces_domain_and_rejects_localhost():
    """Validates that Caddyfile rejects localhost/IP headers in production."""
    caddyfile_path = os.path.join(REPO_ROOT, "Caddyfile")
    with open(caddyfile_path, "r", encoding="utf-8") as f:
        caddy_text = f.read()

    assert "@forbidden_hosts" in caddy_text
    assert "header Host localhost* 127.0.0.1*" in caddy_text
    assert 'respond @forbidden_hosts "Production reverse proxy requires a configured public domain." 400' in caddy_text


def test_env_production_example_has_all_required_credentials():
    """Validates that .env.production.example documents all production secrets and authenticated URLs."""
    env_example_path = os.path.join(REPO_ROOT, ".env.production.example")
    with open(env_example_path, "r", encoding="utf-8") as f:
        env_text = f.read()

    required_keys = [
        "DOMAIN_NAME",
        "JWT_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "RABBITMQ_DEFAULT_PASS",
        "MINIO_ROOT_PASSWORD",
        "REDIS_URL",
        "CELERY_RESULT_BACKEND",
        "CELERY_BROKER_URL",
        "DATABASE_URL",
    ]
    for key in required_keys:
        assert re.search(rf"^{key}=", env_text, re.MULTILINE), f".env.production.example must document {key}"


