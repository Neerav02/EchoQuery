import pytest
import os
import sys
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from config import Settings, DEFAULT_JWT_SECRET_KEY
from database import Base, SessionLocal as TestingSession
from main import app
from events import publish_job_event
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


# ==========================================
# 4. Production JWT Secret Validation Tests
# ==========================================

@pytest.mark.parametrize(
    "bad_secret",
    [
        DEFAULT_JWT_SECRET_KEY,
        "",
        "   ",
        "changeme",
        "too-short-for-production-hs256",
        "multibyte-\u00e9-short-29-bytes!",
    ],
)
def test_production_rejects_default_or_weak_jwt_secret(bad_secret):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ENVIRONMENT="production", JWT_SECRET_KEY=bad_secret)


def test_production_rejects_weak_fallback_jwt_secret():
    strong_primary = "prod-primary-signing-key-with-32-plus-bytes!"
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ENVIRONMENT="Production",
            JWT_SECRET_KEY=strong_primary,
            JWT_SECRET_KEY_FALLBACK="too-short",
        )


def test_production_accepts_strong_non_default_jwt_secrets():
    strong_primary = "prod-primary-signing-key-with-32-plus-bytes!"
    strong_fallback = "prod-fallback-signing-key-with-32-plus-bytes!"
    cfg = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        JWT_SECRET_KEY=strong_primary,
        JWT_SECRET_KEY_FALLBACK=strong_fallback,
    )
    assert cfg.JWT_SECRET_KEY == strong_primary
    assert cfg.JWT_SECRET_KEY_FALLBACK == strong_fallback


@pytest.mark.parametrize("env_name", ["development", "test"])
def test_non_production_preserves_default_jwt_secret(env_name):
    cfg = Settings(_env_file=None, ENVIRONMENT=env_name)
    assert cfg.JWT_SECRET_KEY == DEFAULT_JWT_SECRET_KEY


# ==========================================
# 5. WebSocket Auth & Job Ownership Tests
# ==========================================

def _seed_ws_users_and_job():
    db = TestingSession()
    owner = models.User(
        email="ws_owner@echoquery.io",
        hashed_password=hash_password("OwnerPass123!"),
        is_superuser=False,
        password_migrated=True,
    )
    other = models.User(
        email="ws_other@echoquery.io",
        hashed_password=hash_password("OtherPass123!"),
        is_superuser=False,
        password_migrated=True,
    )
    admin = models.User(
        email="ws_admin@echoquery.io",
        hashed_password=hash_password("AdminPass123!"),
        is_superuser=True,
        password_migrated=True,
    )
    db.add_all([owner, other, admin])
    db.commit()
    db.refresh(owner)
    db.refresh(other)
    db.refresh(admin)

    job = models.Job(
        user_id=owner.id,
        filename="ws_owner_audio.mp3",
        storage_name="ws-owner-storage",
        status="PENDING",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    ids = (owner.id, other.id, admin.id, job.id)
    db.close()
    return ids


def test_websocket_rejects_unauthenticated_and_invalid_tokens(monkeypatch):
    owner_id, _, _, job_id = _seed_ws_users_and_job()
    access_token, _ = create_access_token({"sub": str(owner_id), "email": "ws_owner@echoquery.io"})
    refresh_token, _ = create_refresh_token({"sub": str(owner_id), "email": "ws_owner@echoquery.io"})
    expired_token, _ = create_access_token(
        {"sub": str(owner_id), "email": "ws_owner@echoquery.io"},
        expires_delta=timedelta(minutes=-5),
    )

    with TestClient(app) as client:
        # 1. Missing token
        with pytest.raises(WebSocketDisconnect) as exc_unauth:
            with client.websocket_connect(f"/ws/stream/{job_id}"):
                pass
        assert exc_unauth.value.code == 1008

        # 2. Malformed token
        with pytest.raises(WebSocketDisconnect) as exc_bad:
            with client.websocket_connect(
                f"/ws/stream/{job_id}",
                headers={"Authorization": "Bearer not-a-valid-jwt"},
            ):
                pass
        assert exc_bad.value.code == 1008

        # 3. Refresh token rejected on stream endpoint
        with pytest.raises(WebSocketDisconnect) as exc_ref:
            with client.websocket_connect(f"/ws/stream/{job_id}?token={refresh_token}"):
                pass
        assert exc_ref.value.code == 1008

        # 4. Expired access token rejected
        with pytest.raises(WebSocketDisconnect) as exc_exp:
            with client.websocket_connect(
                f"/ws/stream/{job_id}",
                headers={"Authorization": f"Bearer {expired_token}"},
            ):
                pass
        assert exc_exp.value.code == 1008

        # 5. Blacklisted access token rejected
        monkeypatch.setattr("main.is_token_blacklisted", lambda _jti: True)
        with pytest.raises(WebSocketDisconnect) as exc_revoked:
            with client.websocket_connect(
                f"/ws/stream/{job_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            ):
                pass
        assert exc_revoked.value.code == 1008


def test_websocket_enforces_job_ownership_and_superuser_access():
    owner_id, other_id, admin_id, job_id = _seed_ws_users_and_job()
    publish_job_event(job_id, "TRANSCRIPT_SEGMENT", {"start_sec": 0.0, "end_sec": 5.0, "text": "Owner stream test"})
    owner_token, _ = create_access_token({"sub": str(owner_id), "email": "ws_owner@echoquery.io"})
    other_token, _ = create_access_token({"sub": str(other_id), "email": "ws_other@echoquery.io"})
    admin_token, _ = create_access_token({"sub": str(admin_id), "email": "ws_admin@echoquery.io"})

    with TestClient(app) as client:
        # Non-owner cannot stream another user's job
        with pytest.raises(WebSocketDisconnect) as exc_other:
            with client.websocket_connect(
                f"/ws/stream/{job_id}",
                headers={"Authorization": f"Bearer {other_token}"},
            ):
                pass
        assert exc_other.value.code == 1008

        # Non-existent job ID is rejected
        with pytest.raises(WebSocketDisconnect) as exc_missing:
            with client.websocket_connect(
                "/ws/stream/999999",
                headers={"Authorization": f"Bearer {owner_token}"},
            ):
                pass
        assert exc_missing.value.code == 1008

        # Owner succeeds via Authorization header
        with client.websocket_connect(
            f"/ws/stream/{job_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        ) as ws:
            msg = ws.receive_json()
            assert "event_type" in msg and "data" in msg

        # Owner succeeds via query parameter token
        with client.websocket_connect(f"/ws/stream/{job_id}?token={owner_token}") as ws:
            msg = ws.receive_json()
            assert "event_type" in msg and "data" in msg

        # Superuser can stream another user's job
        with client.websocket_connect(
            f"/ws/stream/{job_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        ) as ws:
            msg = ws.receive_json()
            assert "event_type" in msg and "data" in msg


def _seed_ownerless_and_owned_jobs():
    db = TestingSession()
    owner = models.User(
        email="auth_owner@echoquery.io",
        hashed_password=hash_password("OwnerPass123!"),
        is_superuser=False,
        password_migrated=True,
    )
    other = models.User(
        email="auth_other@echoquery.io",
        hashed_password=hash_password("OtherPass123!"),
        is_superuser=False,
        password_migrated=True,
    )
    admin = models.User(
        email="auth_admin@echoquery.io",
        hashed_password=hash_password("AdminPass123!"),
        is_superuser=True,
        password_migrated=True,
    )
    db.add_all([owner, other, admin])
    db.commit()
    db.refresh(owner)
    db.refresh(other)
    db.refresh(admin)

    owned_job = models.Job(
        user_id=owner.id,
        filename="owned_audio.mp3",
        storage_name="owned-storage",
        status="PENDING",
    )
    ownerless_job = models.Job(
        user_id=None,
        filename="ownerless_audio.mp3",
        storage_name="ownerless-storage",
        status="PENDING",
    )
    db.add_all([owned_job, ownerless_job])
    db.commit()
    db.refresh(owned_job)
    db.refresh(ownerless_job)
    ids = (owner.id, other.id, admin.id, owned_job.id, ownerless_job.id)
    db.close()
    return ids


def test_http_job_access_enforces_owner_superuser_and_ownerless_rules():
    owner_id, other_id, admin_id, owned_job_id, ownerless_job_id = _seed_ownerless_and_owned_jobs()
    owner_token, _ = create_access_token({"sub": str(owner_id), "email": "auth_owner@echoquery.io"})
    other_token, _ = create_access_token({"sub": str(other_id), "email": "auth_other@echoquery.io"})
    admin_token, _ = create_access_token({"sub": str(admin_id), "email": "auth_admin@echoquery.io"})

    with TestClient(app) as client:
        # Unauthenticated HTTP access to ownerless job and owned job is rejected
        unauth_ownerless = client.get(f"/jobs/{ownerless_job_id}")
        assert unauth_ownerless.status_code in (401, 403)
        unauth_owned = client.get(f"/jobs/{owned_job_id}")
        assert unauth_owned.status_code in (401, 403)

        # Non-superuser cannot access ownerless job
        other_ownerless = client.get(
            f"/jobs/{ownerless_job_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert other_ownerless.status_code == 403

        # Superuser can access ownerless job
        admin_ownerless = client.get(
            f"/jobs/{ownerless_job_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_ownerless.status_code == 200
        assert admin_ownerless.json()["job_id"] == ownerless_job_id

        # Owned job: owner succeeds, non-owner rejected, superuser succeeds
        res_owner = client.get(
            f"/jobs/{owned_job_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res_owner.status_code == 200
        assert res_owner.json()["job_id"] == owned_job_id

        res_other = client.get(
            f"/jobs/{owned_job_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert res_other.status_code == 403

        res_admin = client.get(
            f"/jobs/{owned_job_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_admin.status_code == 200
        assert res_admin.json()["job_id"] == owned_job_id


def test_websocket_ownerless_job_requires_superuser():
    _, other_id, admin_id, _, ownerless_job_id = _seed_ownerless_and_owned_jobs()
    publish_job_event(ownerless_job_id, "TRANSCRIPT_SEGMENT", {"start_sec": 0.0, "end_sec": 5.0, "text": "Ownerless stream test"})
    other_token, _ = create_access_token({"sub": str(other_id), "email": "auth_other@echoquery.io"})
    admin_token, _ = create_access_token({"sub": str(admin_id), "email": "auth_admin@echoquery.io"})

    with TestClient(app) as client:
        # Unauthenticated cannot stream ownerless job
        with pytest.raises(WebSocketDisconnect) as exc_unauth:
            with client.websocket_connect(f"/ws/stream/{ownerless_job_id}"):
                pass
        assert exc_unauth.value.code == 1008

        # Authenticated non-superuser cannot stream ownerless job
        with pytest.raises(WebSocketDisconnect) as exc_other:
            with client.websocket_connect(
                f"/ws/stream/{ownerless_job_id}",
                headers={"Authorization": f"Bearer {other_token}"},
            ):
                pass
        assert exc_other.value.code == 1008

        # Superuser can stream ownerless job
        with client.websocket_connect(
            f"/ws/stream/{ownerless_job_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        ) as ws:
            msg = ws.receive_json()
            assert "event_type" in msg and "data" in msg

