import re
import hmac
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
import bcrypt
import jwt
from jwt.exceptions import PyJWTError, ExpiredSignatureError
from sqlalchemy.orm import Session

from config import settings
from redis_lock import get_redis_client

logger = logging.getLogger("echoquery.security")

# Regex pattern for standard Bcrypt hashes ($2a$, $2b$, $2y$)
BCRYPT_PATTERN = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")

def is_bcrypt_hash(hash_candidate: Optional[str]) -> bool:
    """Checks whether a string follows the modular Bcrypt hash format."""
    if not hash_candidate or not isinstance(hash_candidate, str):
        return False
    return bool(BCRYPT_PATTERN.match(hash_candidate))

def hash_password(password: str) -> str:
    """Generates a secure Bcrypt hash with 12 salt rounds."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a Bcrypt hash."""
    if not is_bcrypt_hash(hashed_password):
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception as e:
        logger.error(f"Error checking bcrypt password: {e}")
        return False

def verify_and_migrate_password(plain_password: str, user: Any, db: Session) -> bool:
    """
    Transparent On-Login Rehash:
    1. If user password is an active Bcrypt hash and marked as migrated, verifies standard hash.
    2. If user password is an unmigrated legacy plaintext string, performs a constant-time
       comparison. If matched, immediately upgrades to Bcrypt and commits to DB.
    """
    is_migrated = getattr(user, "password_migrated", False)
    stored_credential = user.hashed_password

    if is_migrated and is_bcrypt_hash(stored_credential):
        return verify_password(plain_password, stored_credential)

    # Legacy credential check (constant-time comparison to prevent timing attacks)
    matched = hmac.compare_digest(stored_credential, plain_password)
    if matched:
        try:
            new_hash = hash_password(plain_password)
            user.hashed_password = new_hash
            user.password_migrated = True
            db.commit()
            db.refresh(user)
            logger.info(f"Successfully migrated legacy plaintext password to Bcrypt for User ID #{user.id}")
        except Exception as e:
            logger.error(f"Failed to commit password migration for User ID #{user.id}: {e}")
            db.rollback()
        return True

    return False

# --- JWT Token Management ---

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> Tuple[str, str]:
    """Issues an access token with a unique jti."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    jti = str(uuid.uuid4())
    
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": jti,
        "type": "access"
    })
    
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti

def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> Tuple[str, str]:
    """Issues a long-lived refresh token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    jti = str(uuid.uuid4())
    
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": jti,
        "type": "refresh"
    })
    
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti

def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token.
    Supports zero-downtime secret rotation by attempting JWT_SECRET_KEY_FALLBACK if primary fails.
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise
    except PyJWTError:
        if settings.JWT_SECRET_KEY_FALLBACK:
            return jwt.decode(token, settings.JWT_SECRET_KEY_FALLBACK, algorithms=[settings.JWT_ALGORITHM])
        raise

# --- Token Revocation (Redis Denylist) ---

def blacklist_token(jti: str, expires_in_sec: int) -> bool:
    """Adds a JWT ID to the Redis revocation blacklist."""
    client = get_redis_client()
    if client and expires_in_sec > 0:
        try:
            client.setex(f"blacklist:jti:{jti}", expires_in_sec, "revoked")
            logger.info(f"Token jti '{jti}' successfully added to revocation blacklist.")
            return True
        except Exception as e:
            logger.error(f"Failed to blacklist token jti '{jti}': {e}")
    return False

def is_token_blacklisted(jti: str) -> bool:
    """Checks whether a token jti is revoked."""
    client = get_redis_client()
    if client:
        try:
            return bool(client.exists(f"blacklist:jti:{jti}"))
        except Exception as e:
            logger.warning(f"Error checking token blacklist for '{jti}': {e}")
    return False

# --- Rate Limiting (Token Bucket in Redis) ---

def check_login_rate_limit(identifier: str, max_attempts: int = 5, window_sec: int = 900) -> bool:
    """
    Checks if login attempts for an IP or email address exceed threshold.
    Returns True if allowed, False if rate-limited.
    """
    client = get_redis_client()
    if not client:
        return True  # Fallback if Redis is unavailable in development

    key = f"ratelimit:login:{identifier}"
    try:
        attempts = client.get(key)
        if attempts and int(attempts) >= max_attempts:
            return False
        return True
    except Exception as e:
        logger.warning(f"Rate limit check failed: {e}")
        return True

def record_failed_login(identifier: str, window_sec: int = 900) -> int:
    """Increments the failed login counter for an IP or email address."""
    client = get_redis_client()
    if not client:
        return 1

    key = f"ratelimit:login:{identifier}"
    try:
        current = client.incr(key)
        if current == 1:
            client.expire(key, window_sec)
        return current
    except Exception as e:
        logger.warning(f"Failed to record rate limit count: {e}")
        return 1

def reset_login_rate_limit(identifier: str) -> None:
    """Resets the rate limit counter upon successful authentication."""
    client = get_redis_client()
    if client:
        try:
            client.delete(f"ratelimit:login:{identifier}")
        except Exception as e:
            logger.warning(f"Failed to reset login rate limit for '{identifier}': {e}")

