import os
import tempfile
import shutil
import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command

import models

def test_alembic_heads_single_linear_history():
    """Validates that Alembic history has a single head and unbroken revision lineage."""
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 Alembic head, found: {heads}"
    assert heads[0] == "23a242a11396", f"Expected head to be 23a242a11396, found: {heads[0]}"
    
    rev = script.get_revision("23a242a11396")
    assert rev.down_revision == "bb3e66028d93"
    
    prev_rev = script.get_revision("bb3e66028d93")
    assert prev_rev.down_revision == "a43181a5d516"
    
    base_rev = script.get_revision("a43181a5d516")
    assert base_rev.down_revision is None

def test_models_declare_required_constraints():
    """Validates that SQLAlchemy models declare the strict nullability, types, and indexes."""
    # User model constraints
    assert models.User.__table__.columns["email"].nullable is False
    assert models.User.__table__.columns["hashed_password"].nullable is False
    
    # Job model constraints
    assert models.Job.__table__.columns["filename"].nullable is False
    assert models.Job.__table__.columns["storage_name"].nullable is False
    assert isinstance(models.Job.__table__.columns["transcript"].type, sa.Text)
    assert isinstance(models.Job.__table__.columns["summary"].type, sa.Text)
    assert models.Job.__table__.columns["status"].index is True

def test_schema_alignment_migration_upgrade_and_downgrade():
    """
    Simulates applying migration 23a242a11396 on an isolated database with legacy schema
    and verifies that all 7 schema drift discrepancies are resolved upon upgrade
    and safely restored upon downgrade.
    """
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "mig_test.db").replace("\\", "/")
    temp_url = f"sqlite:///{temp_db_path}"
    
    try:
        engine = sa.create_engine(temp_url)
        with engine.connect() as conn:
            # Create legacy schema matching pre-migration state (nullable=True, VARCHAR, no status index)
            conn.execute(sa.text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR,
                    hashed_password VARCHAR,
                    is_superuser BOOLEAN DEFAULT 0 NOT NULL,
                    password_migrated BOOLEAN DEFAULT 0 NOT NULL,
                    created_at TIMESTAMP
                );
            """))
            conn.execute(sa.text("""
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY,
                    filename VARCHAR,
                    storage_name VARCHAR,
                    status VARCHAR,
                    transcript VARCHAR,
                    summary VARCHAR,
                    sentiment VARCHAR,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    execution_time_ms FLOAT,
                    is_dlq BOOLEAN DEFAULT 0,
                    lock_acquired BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    user_id INTEGER,
                    storage_bucket VARCHAR,
                    idempotency_key VARCHAR(64),
                    lock_token VARCHAR(64),
                    ai_provider VARCHAR,
                    ai_model VARCHAR,
                    token_usage INTEGER
                );
            """))
            conn.execute(sa.text("""
                CREATE TABLE refresh_tokens (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    token VARCHAR NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    revoked BOOLEAN NOT NULL,
                    created_at TIMESTAMP
                );
            """))
            conn.execute(sa.text("""
                CREATE TABLE outbox_tasks (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER NOT NULL,
                    topic VARCHAR NOT NULL,
                    payload TEXT NOT NULL,
                    status VARCHAR,
                    retry_count INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP,
                    dispatched_at TIMESTAMP
                );
            """))
            conn.execute(sa.text("""
                CREATE TABLE alembic_version (
                    version_num VARCHAR(32) NOT NULL PRIMARY KEY
                );
            """))
            conn.execute(sa.text("INSERT INTO alembic_version VALUES ('bb3e66028d93');"))
            conn.commit()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", temp_url)

        # 1. Execute Upgrade to 23a242a11396
        command.upgrade(cfg, "23a242a11396")

        # 2. Assert all 7 schema differences resolved
        inspector = sa.inspect(engine)
        user_cols = {c["name"]: c for c in inspector.get_columns("users")}
        job_cols = {c["name"]: c for c in inspector.get_columns("jobs")}
        job_idx = [i["name"] for i in inspector.get_indexes("jobs")]

        # (1) jobs.filename NOT NULL
        assert job_cols["filename"]["nullable"] is False
        # (2) jobs.storage_name NOT NULL
        assert job_cols["storage_name"]["nullable"] is False
        # (3) jobs.transcript TEXT
        assert isinstance(job_cols["transcript"]["type"], sa.Text)
        # (4) jobs.summary TEXT
        assert isinstance(job_cols["summary"]["type"], sa.Text)
        # (5) index ix_jobs_status
        assert "ix_jobs_status" in job_idx
        # (6) users.email NOT NULL
        assert user_cols["email"]["nullable"] is False
        # (7) users.hashed_password NOT NULL
        assert user_cols["hashed_password"]["nullable"] is False

        # 3. Execute Downgrade to bb3e66028d93
        command.downgrade(cfg, "bb3e66028d93")

        # 4. Assert reversal
        inspector = sa.inspect(engine)
        user_cols_post = {c["name"]: c for c in inspector.get_columns("users")}
        job_cols_post = {c["name"]: c for c in inspector.get_columns("jobs")}
        job_idx_post = [i["name"] for i in inspector.get_indexes("jobs")]

        assert user_cols_post["email"]["nullable"] is True
        assert user_cols_post["hashed_password"]["nullable"] is True
        assert job_cols_post["filename"]["nullable"] is True
        assert job_cols_post["storage_name"]["nullable"] is True
        assert "ix_jobs_status" not in job_idx_post

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_migration_aborts_on_unexpected_null_values():
    """
    Validates that if existing rows contain NULL values in affected columns,
    migration 23a242a11396 raises an explicit RuntimeError rather than
    silently inserting placeholder data or corrupting existing records.
    """
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "mig_null_test.db").replace("\\", "/")
    temp_url = f"sqlite:///{temp_db_path}"
    
    try:
        engine = sa.create_engine(temp_url)
        with engine.connect() as conn:
            conn.execute(sa.text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR,
                    hashed_password VARCHAR,
                    is_superuser BOOLEAN DEFAULT 0 NOT NULL,
                    password_migrated BOOLEAN DEFAULT 0 NOT NULL,
                    created_at TIMESTAMP
                );
            """))
            conn.execute(sa.text("""
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY,
                    filename VARCHAR,
                    storage_name VARCHAR,
                    status VARCHAR,
                    transcript VARCHAR,
                    summary VARCHAR,
                    sentiment VARCHAR,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    execution_time_ms FLOAT,
                    is_dlq BOOLEAN DEFAULT 0,
                    lock_acquired BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    user_id INTEGER,
                    storage_bucket VARCHAR,
                    idempotency_key VARCHAR(64),
                    lock_token VARCHAR(64),
                    ai_provider VARCHAR,
                    ai_model VARCHAR,
                    token_usage INTEGER
                );
            """))
            conn.execute(sa.text("""
                CREATE TABLE refresh_tokens (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    token VARCHAR NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    revoked BOOLEAN NOT NULL,
                    created_at TIMESTAMP
                );
            """))
            conn.execute(sa.text("""
                CREATE TABLE outbox_tasks (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER NOT NULL,
                    topic VARCHAR NOT NULL,
                    payload TEXT NOT NULL,
                    status VARCHAR,
                    retry_count INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP,
                    dispatched_at TIMESTAMP
                );
            """))
            conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY);"))
            conn.execute(sa.text("INSERT INTO alembic_version VALUES ('bb3e66028d93');"))
            
            # Insert a record with NULL email and NULL filename to simulate pre-existing NULLs
            conn.execute(sa.text("INSERT INTO users (id, email, hashed_password) VALUES (1, NULL, 'hash123');"))
            conn.execute(sa.text("INSERT INTO jobs (id, filename, storage_name) VALUES (1, NULL, 'storage123');"))
            conn.commit()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", temp_url)

        with pytest.raises(Exception) as exc_info:
            command.upgrade(cfg, "23a242a11396")

        assert "Migration 23a242a11396 aborted" in str(exc_info.value)
        assert "users.email: 1" in str(exc_info.value)
        assert "jobs.filename: 1" in str(exc_info.value)

        # Confirm data was not modified or overwritten with dummy values
        with engine.connect() as conn:
            user_email = conn.execute(sa.text("SELECT email FROM users WHERE id = 1")).scalar()
            job_file = conn.execute(sa.text("SELECT filename FROM jobs WHERE id = 1")).scalar()
            assert user_email is None, "Migration must not overwrite or inject placeholder into users.email"
            assert job_file is None, "Migration must not overwrite or inject placeholder into jobs.filename"

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_fresh_database_full_upgrade_from_scratch():
    """
    Validates REQ-DB-01: An empty database with zero tables upgrades cleanly
    through a43181a5d516 -> bb3e66028d93 -> 23a242a11396 without errors,
    creates all tables and constraints, and matches SQLAlchemy models.
    """
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "fresh_db.db").replace("\\", "/")
    temp_url = f"sqlite:///{temp_db_path}"

    try:
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", temp_url)

        # 1. Upgrade from scratch
        command.upgrade(cfg, "head")

        # 2. Verify all tables exist
        engine = sa.create_engine(temp_url)
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"users", "jobs", "refresh_tokens", "outbox_tasks", "alembic_version"}.issubset(tables)

        # 3. Verify columns, types, indexes, and constraints
        user_cols = {c["name"]: c for c in inspector.get_columns("users")}
        job_cols = {c["name"]: c for c in inspector.get_columns("jobs")}
        user_idx = [i["name"] for i in inspector.get_indexes("users")]
        job_idx = [i["name"] for i in inspector.get_indexes("jobs")]

        assert user_cols["email"]["nullable"] is False
        assert user_cols["hashed_password"]["nullable"] is False
        assert "ix_users_email" in user_idx
        assert job_cols["filename"]["nullable"] is False
        assert job_cols["storage_name"]["nullable"] is False
        assert isinstance(job_cols["transcript"]["type"], sa.Text)
        assert isinstance(job_cols["summary"]["type"], sa.Text)
        assert "ix_jobs_status" in job_idx

        # 4. Verify model-schema consistency with alembic check
        command.check(cfg)

        # 5. Verify downgrade and re-upgrade cycle
        command.downgrade(cfg, "bb3e66028d93")
        command.downgrade(cfg, "a43181a5d516")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        command.check(cfg)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_postgresql_offline_sql_generation():
    """
    Validates offline PostgreSQL DDL generation for all migrations without
    requiring a live PostgreSQL server.
    """
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", "postgresql://echo_user:echo_password@db:5432/echo_db")
    # Generates offline SQL for full migration chain
    command.upgrade(cfg, "head", sql=True)


