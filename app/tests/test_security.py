import pytest
import os
import sys
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from database import Base, SessionLocal as TestingSession
from main import app
from security import (
    hash_password, verify_password, is_bcrypt_hash,
    verify_and_migrate_password, create_access_token, create_refresh_token,
    decode_token
)

# ==========================================
# 1. Password Hashing & Legacy Migration Tests
# ==========================================

def test_bcrypt_hashing_and_verification():
    raw_pass = "SecurePass123!$"
    hashed = hash_password(raw_pass)
    
    assert is_bcrypt_hash(hashed)
    assert hashed.startswith("$2b$12$")
    assert verify_password(raw_pass, hashed)
    assert not verify_password("WrongPassword", hashed)

def test_transparent_on_login_rehash():
    """Verifies safe migration of legacy plaintext password to Bcrypt upon login."""
    db = TestingSession()
    legacy_plain = "legacy_secret_password"
    
    # Seed unmigrated user with plaintext in hashed_password column
    user = models.User(
        email="legacy@echoquery.io",
        hashed_password=legacy_plain,
        password_migrated=False,
        is_superuser=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id

    assert not is_bcrypt_hash(user.hashed_password)
    assert user.password_migrated is False

    # Attempt login with wrong password
    failed = verify_and_migrate_password("wrong_password", user, db)
    assert not failed
    assert user.password_migrated is False

    # Attempt login with correct password -> triggers transparent rehash
    success = verify_and_migrate_password(legacy_plain, user, db)
    assert success

    # Verify user record updated in database
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    assert db_user.password_migrated is True
    assert is_bcrypt_hash(db_user.hashed_password)
    assert verify_password(legacy_plain, db_user.hashed_password)
    db.close()

# ==========================================
# 2. JWT Lifecycle & Dual-Key Secret Rotation
# ==========================================

def test_jwt_token_creation_and_claims():
    data = {"sub": "42", "email": "test@echoquery.io"}
    token, jti = create_access_token(data, expires_delta=timedelta(minutes=15))
    
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["email"] == "test@echoquery.io"
    assert payload["jti"] == jti
    assert payload["type"] == "access"
    assert "exp" in payload

def test_jwt_dual_key_rotation(monkeypatch):
    """Verifies that tokens signed with a fallback secret key are accepted during key rotation."""
    import config
    monkeypatch.setattr(config.settings, "JWT_SECRET_KEY", "new_active_secret_key_32_bytes_long!")
    monkeypatch.setattr(config.settings, "JWT_SECRET_KEY_FALLBACK", "old_fallback_secret_key_32_bytes!")
    
    # Sign token with old fallback key
    import jwt
    old_token = jwt.encode(
        {"sub": "99", "email": "rotate@echoquery.io", "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        "old_fallback_secret_key_32_bytes!",
        algorithm="HS256"
    )
    
    # Decode should successfully fall back to old key
    decoded = decode_token(old_token)
    assert decoded["sub"] == "99"

# ==========================================
# 3. API Endpoint Security & Authorization Tests
# ==========================================

def test_user_registration_hashes_password_automatically():
    with TestClient(app) as client:
        res = client.post("/users/", json={"email": "newuser@echoquery.io", "password": "NewSecretPassword123!"})
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "newuser@echoquery.io"
        
        # Verify in DB that password was hashed
        db = TestingSession()
        u = db.query(models.User).filter(models.User.email == "newuser@echoquery.io").first()
        assert is_bcrypt_hash(u.hashed_password)
        assert u.password_migrated is True
        db.close()

def test_auth_login_and_token_generation():
    with TestClient(app) as client:
        # Register user
        client.post("/users/", json={"email": "loginuser@echoquery.io", "password": "MyLoginPassword123!"})
        
        # Test OAuth2 form login
        login_res = client.post("/auth/token", data={"username": "loginuser@echoquery.io", "password": "MyLoginPassword123!"})
        assert login_res.status_code == 200
        token_data = login_res.json()
        assert "access_token" in token_data
        assert "refresh_token" in token_data
        assert token_data["token_type"] == "bearer"
        
        # Test wrong password
        fail_res = client.post("/auth/token", data={"username": "loginuser@echoquery.io", "password": "WrongPassword"})
        assert fail_res.status_code == 401

def test_refresh_token_lifecycle_and_rotation():
    with TestClient(app) as client:
        client.post("/users/", json={"email": "refreshuser@echoquery.io", "password": "RefreshPassword123!"})
        login_res = client.post("/auth/token", data={"username": "refreshuser@echoquery.io", "password": "RefreshPassword123!"})
        tokens = login_res.json()
        initial_refresh = tokens["refresh_token"]

        # Request new access token using refresh token
        ref_res = client.post("/auth/refresh", json={"refresh_token": initial_refresh})
        assert ref_res.status_code == 200
        new_tokens = ref_res.json()
        assert "access_token" in new_tokens
        assert new_tokens["refresh_token"] != initial_refresh

        # Re-using the old refresh token must be rejected (Token Rotation)
        reused_res = client.post("/auth/refresh", json={"refresh_token": initial_refresh})
        assert reused_res.status_code == 401

def test_upload_route_requires_authentication(mocker):
    mocker.patch("main.upload_file_stream")
    mocker.patch("main.execute_job_compute_logic")

    with TestClient(app) as client:
        files = {"file": ("audio_sample.mp3", b"test audio content", "audio/mpeg")}
        
        # Unauthenticated request must be rejected
        unauth_res = client.post("/upload/", files=files)
        assert unauth_res.status_code == 401

        # Register and get auth token
        client.post("/users/", json={"email": "uploader@echoquery.io", "password": "UploadPassword123!"})
        auth_res = client.post("/auth/token", data={"username": "uploader@echoquery.io", "password": "UploadPassword123!"})
        token = auth_res.json()["access_token"]

        # Authenticated upload succeeds
        headers = {"Authorization": f"Bearer {token}"}
        auth_upload = client.post("/upload/", files={"file": ("audio_sample.mp3", b"test audio content", "audio/mpeg")}, headers=headers)
        assert auth_upload.status_code == 200
        assert "job_id" in auth_upload.json()

def test_resource_ownership_and_access_control():
    with TestClient(app) as client:
        # Register User A and User B
        client.post("/users/", json={"email": "usera@echoquery.io", "password": "PasswordA123!"})
        client.post("/users/", json={"email": "userb@echoquery.io", "password": "PasswordB123!"})

        token_a = client.post("/auth/token", data={"username": "usera@echoquery.io", "password": "PasswordA123!"}).json()["access_token"]
        token_b = client.post("/auth/token", data={"username": "userb@echoquery.io", "password": "PasswordB123!"}).json()["access_token"]

        # Seed job owned by User A
        db = TestingSession()
        user_a = db.query(models.User).filter(models.User.email == "usera@echoquery.io").first()
        job = models.Job(user_id=user_a.id, filename="usera_file.mp3", storage_name="usera_storage", status="PENDING")
        db.add(job)
        db.commit()
        job_id = job.id
        db.close()

        # User A can access own job
        res_a = client.get(f"/jobs/{job_id}", headers={"Authorization": f"Bearer {token_a}"})
        assert res_a.status_code == 200
        assert res_a.json()["job_id"] == job_id

        # User B cannot access User A's job -> HTTP 403 Forbidden
        res_b = client.get(f"/jobs/{job_id}", headers={"Authorization": f"Bearer {token_b}"})
        assert res_b.status_code == 403

def test_dlq_endpoints_require_superuser_privileges():
    with TestClient(app) as client:
        # Regular user
        client.post("/users/", json={"email": "regular@echoquery.io", "password": "RegularPassword123!"})
        token_regular = client.post("/auth/token", data={"username": "regular@echoquery.io", "password": "RegularPassword123!"}).json()["access_token"]

        # Superuser (Admin)
        db = TestingSession()
        admin = models.User(
            email="admin_tester@echoquery.io",
            hashed_password=hash_password("AdminPass123!"),
            is_superuser=True,
            password_migrated=True
        )
        db.add(admin)
        db.commit()
        db.close()
        token_admin = client.post("/auth/token", data={"username": "admin_tester@echoquery.io", "password": "AdminPass123!"}).json()["access_token"]

        # Regular user accessing /dlq/jobs -> HTTP 403 Forbidden
        res_regular = client.get("/dlq/jobs", headers={"Authorization": f"Bearer {token_regular}"})
        assert res_regular.status_code == 403

        # Admin accessing /dlq/jobs -> HTTP 200 OK
        res_admin = client.get("/dlq/jobs", headers={"Authorization": f"Bearer {token_admin}"})
        assert res_admin.status_code == 200

