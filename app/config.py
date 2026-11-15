import os
import socket
from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET_KEY = "echoquery-production-secret-key-minimum-32-bytes-secure!"
INSECURE_JWT_PLACEHOLDERS = {
    DEFAULT_JWT_SECRET_KEY,
    "changeme",
    "secret",
    "secret-key",
    "replace-me",
    "placeholder",
    "your-secret-key",
    "your-production-secret-key",
}
MIN_JWT_SECRET_BYTES = 32


def _validate_production_jwt_secret(secret: str, field_name: str) -> None:
    """Reject empty, placeholder, default, or short JWT secrets in production."""
    normalized = (secret or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty when ENVIRONMENT='production'.")
    if normalized in INSECURE_JWT_PLACEHOLDERS or normalized.lower() in INSECURE_JWT_PLACEHOLDERS:
        raise ValueError(
            f"{field_name} must be overridden from default or placeholder values when ENVIRONMENT='production'."
        )
    if len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
        raise ValueError(
            f"{field_name} must be at least {MIN_JWT_SECRET_BYTES} UTF-8 bytes when ENVIRONMENT='production'."
        )


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "EchoQuery Distributed Task Engine"
    ENVIRONMENT: str = "development"  # development, test, production
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "sqlite:///./echo_local.db"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    
    # Security & JWT
    JWT_SECRET_KEY: str = DEFAULT_JWT_SECRET_KEY
    JWT_SECRET_KEY_FALLBACK: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8501,http://localhost:3000,http://localhost:8000,https://echoquery.onrender.com"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # RabbitMQ / Celery
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5672//"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    
    # Storage
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_BUCKET_NAME: str = "echo-bucket"
    AWS_ACCESS_KEY_ID: str = "minio_user"
    AWS_SECRET_ACCESS_KEY: str = "minio_password"
    AWS_REGION: str = "us-east-1"
    
    # AI Providers
    AI_PRIMARY_PROVIDER: str = "mock"  # "mock", "openai", "gemini", "local_whisper"
    AI_FALLBACK_PROVIDER: Optional[str] = "mock"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_AUDIO_MODEL: str = "whisper-1"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    WHISPER_MODEL_SIZE: str = "base"
    WHISPER_DEVICE: str = "auto"
    
    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def effective_database_url(self) -> str:
        url = self.DATABASE_URL
        if "@db:" in url or "db:5432" in url:
            try:
                socket.gethostbyname("db")
            except socket.gaierror:
                # When running on host outside Docker network, check if container port 5433 is available
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.3)
                    res = s.connect_ex(("localhost", 5434))
                    s.close()
                    if res == 0:
                        return url.replace("@db:5432", "@localhost:5434").replace("@db", "@localhost:5434")
                except Exception:
                    pass
                return "sqlite:///./echo_local.db"
        return url

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Enforce non-default, strong JWT secrets when running in production."""
        env = (self.ENVIRONMENT or "").strip().lower()
        if env == "production":
            _validate_production_jwt_secret(self.JWT_SECRET_KEY, "JWT_SECRET_KEY")
            if self.JWT_SECRET_KEY_FALLBACK is not None and self.JWT_SECRET_KEY_FALLBACK != "":
                _validate_production_jwt_secret(self.JWT_SECRET_KEY_FALLBACK, "JWT_SECRET_KEY_FALLBACK")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
