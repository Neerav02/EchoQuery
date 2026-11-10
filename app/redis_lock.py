import os
import time
import uuid
import logging
from contextlib import contextmanager
from typing import Optional, Tuple
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

logger = logging.getLogger("echoquery.redis")

_redis_client = None

# Atomic Lua script: only delete the key if the value matches the owner's token
LUA_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}). Running with dummy lock for dev/test mode.")
            _redis_client = False
    return _redis_client if _redis_client is not False else None

class LockResult:
    """Wrapper that evaluates as a boolean for backward compatibility while providing the lock ownership token."""
    def __init__(self, acquired: bool, token: Optional[str] = None, lock_name: Optional[str] = None):
        self.acquired = acquired
        self.token = token
        self.lock_name = lock_name

    def __bool__(self) -> bool:
        return self.acquired

    def __iter__(self):
        return iter((self.acquired, self.token))

    def __repr__(self):
        return f"LockResult(acquired={self.acquired}, token={self.token})"

def release_lock_with_token(lock_name: str, token: str) -> bool:
    """Explicitly releases a distributed lock only if the token matches ownership."""
    client = get_redis_client()
    if not client or not token:
        return True
    try:
        key = f"lock:{lock_name}"
        res = client.eval(LUA_RELEASE_SCRIPT, 1, key, token)
        return bool(res)
    except Exception as e:
        logger.warning(f"Error releasing lock {lock_name} with token: {e}")
        return False

@contextmanager
def distributed_lock(lock_name: str, timeout: int = 15, blocking_timeout: int = 5):
    """
    Distributed lock mechanism using Redis with unique ownership token validation.
    Guarantees mutual exclusion and prevents releasing locks acquired by other processes after timeouts.
    """
    client = get_redis_client()
    lock_token = str(uuid.uuid4())
    lock_key = f"lock:{lock_name}"
    lock_acquired = False

    if client:
        start_time = time.time()
        while time.time() - start_time < blocking_timeout:
            try:
                # SET key token NX EX timeout
                if client.set(lock_key, lock_token, nx=True, ex=timeout):
                    lock_acquired = True
                    break
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"Error acquiring Redis lock {lock_name}: {e}")
                lock_acquired = False
                break
    else:
        # Fallback for dev/testing environment without active Redis server
        lock_acquired = True

    result = LockResult(acquired=lock_acquired, token=lock_token if lock_acquired else None, lock_name=lock_name)
    try:
        yield result
    finally:
        if client and lock_acquired:
            release_lock_with_token(lock_name, lock_token)
