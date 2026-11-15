# Requirements — EchoQuery v2.0.1 Critical Remediation

## Scope Requirements

### SEC — Authentication & Security (Milestone 1 / Phase 08)
- **REQ-SEC-01:** When `ENVIRONMENT == "production"`, application startup / `Settings` validation MUST reject the development default `JWT_SECRET_KEY`, placeholder keys, and keys shorter than 32 UTF-8 bytes; non-production environments (`development`, `test`) MUST remain functional out of the box.
- **REQ-SEC-02:** `/ws/stream/{job_id}` and `GET /jobs/{job_id}` MUST reject unauthenticated callers (`current_user is None`), restrict ownerless jobs (`job.user_id is None`) to superusers only, and enforce resource ownership (`job.user_id == current_user.id` or `current_user.is_superuser`) for owned jobs before returning data or streaming historical/live events.
- **REQ-SEC-03:** Regression tests MUST verify both production `JWT_SECRET_KEY` rejection/acceptance and WebSocket authentication + cross-user access denial.

### DB — Database & Migrations (Milestone 2 / Phase 09)
- **REQ-DB-01:** `alembic upgrade head` MUST succeed from a completely empty database (`0` tables) through revisions `a43181a5d516 -> bb3e66028d93 -> 23a242a11396`.
- **REQ-DB-02:** Revision IDs (`a43181a5d516`, `bb3e66028d93`, `23a242a11396`) and upgrade idempotency MUST be preserved so existing legacy or already-migrated PostgreSQL databases at `23a242a11396` (including `User #1` and `Jobs #1-#3`) suffer zero breakage or data loss.
- **REQ-DB-03:** Resulting fresh-DB schema MUST match `app/models.py` (`User`, `RefreshToken`, `Job`, `OutboxTask`), including `users.email` uniqueness and non-nullability.
- **REQ-DB-04:** Migration validation MUST execute exclusively against an isolated, disposable database and offline SQL generation, never against the live development/production database.

### INFRA — Docker & Infrastructure (Milestone 3 / Phase 10)
- **REQ-INFRA-01:** `app/Dockerfile` (`EXPOSE`, `HEALTHCHECK`, `CMD`), `docker-compose.yml` (`api` ports, `frontend` `API_URL`), and `frontend/main.py` default URL MUST agree consistently on port `8000`.
- **REQ-INFRA-02:** Container healthcheck MUST target the active FastAPI listener on `localhost:8000` (`/health`).

### TEST — Test Reliability (Milestone 4 / Phase 11)
- **REQ-TEST-01:** Remove the stray `s` in `app/tests/test_celery_and_frontend.py:23` so `test_celery_task_registration_windows_host_layout` runs without raising `NameError: name 's' is not defined`.
- **REQ-TEST-02:** All regression tests across Auth/Security, Migrations, Infrastructure config consistency, and Celery/Frontend MUST pass together under `venv\Scripts\python.exe -m pytest -v`.

---

## Traceability Matrix

| Requirement | Milestone / Phase | Primary Verification |
| --- | --- | --- |
| REQ-SEC-01 | Milestone 1 (Phase 08) | Pytest unit tests on `Settings` |
| REQ-SEC-02 | Milestone 1 (Phase 08) | Pytest `TestClient.websocket_connect` auth/ownership tests |
| REQ-SEC-03 | Milestone 1 (Phase 08) | `app/tests/test_security.py` + `app/tests/test_distributed_streaming.py` |
| REQ-DB-01..04 | Milestone 2 (Phase 09) | `app/tests/test_migrations.py` on disposable temp DB + `alembic upgrade head --sql` |
| REQ-INFRA-01..02 | Milestone 3 (Phase 10) | `docker compose config` + static/config regression test + container health probe |
| REQ-TEST-01..02 | Milestone 4 (Phase 11) | `venv\Scripts\python.exe -m pytest -v` |

