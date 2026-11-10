import os
import socket
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    JWT_SECRET_KEY: str = "echoquery-production-secret-key-minimum-32-bytes-secure!"
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
                return "sqlite:///./echo_local.db"
        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
