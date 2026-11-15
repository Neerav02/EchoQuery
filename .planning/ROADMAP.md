# Roadmap — EchoQuery

## Completed Milestones

- [x] **Milestone v2.0** (Phases `01`–`07`, `2026-11-11`): Production transformation (Auth/Bcrypt/JWT, MinIO & Transactional Outbox, Hybrid AI Router, Local Whisper, Celery + Redis Streams, Observability & Supervision, Benchmarks & Streamlit UI). Recorded in `.planning/MILESTONE-v2.0-COMPLETION.md`.

---

## Active Milestone: v2.0.1 — Critical Remediation

**Goal:** Resolve the 5 validated critical security, migration, container port, and test reliability defects while preserving the EchoQuery v2.0 architecture and deployed database compatibility.

### Overview & Dependency Order

```text
[Phase 08: Milestone 1 — Authentication & Security]
   ├── Task 08-01: Production JWT secret validation (independent)
   └── Task 08-02: WebSocket auth & job ownership (touches test compatibility)
          │
          ├───────────────────────────────────────────────────────────┐
          ▼                                                           ▼
[Phase 09: Milestone 2 — Database & Migrations]          [Phase 10: Milestone 3 — Docker & Infra]
   ├── Task 09-01: Make a43181a5d516 fresh-DB safe           └── Task 10-01: Align API port 8000,
   ├── Task 09-02: Preserve chain & schema parity                          healthcheck, Compose & UI URL
   └── Task 09-03: Validate on disposable DB                                (verify env coupling w/ 08-01)
          │                                                           │
          └───────────────────────────┬───────────────────────────────┘
                                      ▼
                     [Phase 11: Milestone 4 — Test Reliability]
                        ├── Task 11-01: Fix stray `s` NameError in test_celery_and_frontend.py
                        └── Task 11-02: Unified regression & full-suite verification
```

---

## Milestones / Phases

### Milestone 1 (Phase 08): Authentication and Security
- **Status:** Completed & Verified (`35/35` targeted pytest cases passing)
- **Plan:** `.planning/phases/08-auth-security-remediation/08-01-PLAN.md`
- **Depends on:** v2.0 baseline
- **Scope:**
  - Enforce fail-fast validation rejecting default/weak `JWT_SECRET_KEY` when `ENVIRONMENT == "production"`.
  - Authenticate `/ws/stream/{job_id}` and enforce job-owner/superuser authorization before accepting/streaming.
  - Add unit and integration regression tests covering production secret validation and WebSocket auth/ownership.

### Milestone 2 (Phase 09): Database and Migrations
- **Status:** Completed & Verified (Disposable PostgreSQL 17 cluster test + 6/6 test_migrations.py cases passing)
- **Plan:** `.planning/phases/09-database-migrations-remediation/09-01-PLAN.md`
- **Depends on:** Existing Alembic baseline (`env.py` `get_url()` overrides + `a43181a5d516 -> bb3e66028d93 -> 23a242a11396`)
- **Scope:**
  - Repair `a43181a5d516_initial_schema_and_security.py` so a fresh empty database creates base `users` and `jobs` tables cleanly without failing on missing FKs/tables.
  - Preserve existing revision IDs and deployed DB compatibility (`23a242a11396` head, `User #1`, `Jobs #1-#3`), and verify `users.email` uniqueness parity.
  - Validate full `upgrade` / `downgrade` and schema inspection on a separate disposable temporary database (plus PostgreSQL `--sql` offline DDL check).

### Milestone 3 (Phase 10): Docker and Infrastructure
- **Status:** Completed & Verified (Docker Compose validation + 5/5 test_docker_and_infrastructure.py cases passing)
- **Plan:** `.planning/phases/10-docker-infrastructure-remediation/10-01-PLAN.md`
- **Depends on:** Milestone 1 (`Task 08-01` env settings awareness if `ENVIRONMENT=production` is ever enabled in containers)
- **Scope:**
  - Align `app/Dockerfile` (`EXPOSE`, `HEALTHCHECK`, `CMD`), `docker-compose.yml` (`api` port mapping, `frontend` `API_URL`), and `frontend/main.py` default URL on port `8000`.
  - Ensure healthcheck hits a valid lightweight FastAPI endpoint (`/health` or `/docs`) on `localhost:8000`.

### Milestone 4 (Phase 11): Test Reliability
- **Status:** Completed & Verified (84/84 tests passing, 86% coverage, zero failures/skips)
- **Plan:** `.planning/phases/11-test-reliability-remediation/11-01-PLAN.md`
- **Depends on:** Milestones 1, 2, and 3
- **Scope:**
  - Fix the stray `s` runtime `NameError` at `app/tests/test_celery_and_frontend.py:23`.
  - Update `test_websocket_stream_receives_events` for authenticated WS access and consolidate regression coverage for all 4 remediation milestones.
  - Verify the full `pytest` suite passes cleanly without skipped/relaxed assertions.

