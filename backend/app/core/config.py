import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://lms:lms@localhost:5432/lms"
    db_null_pool: bool = False
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-me"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False
    # Origin frontend được phép gọi API kèm cookie. Env CORS_ORIGINS: JSON list hoặc chuỗi phân tách dấu phẩy.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio12345"
    minio_bucket: str = "lms"
    minio_secure: bool = False

    embed_provider: str = "fake"  # fake | gemini
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768
    vision_provider: str = "fake"  # fake | gemini
    vision_model: str = "gemini-2.5-flash"
    gemini_api_key: str = ""
    embed_timeout_s: float = 30.0
    vision_timeout_s: float = 120.0
    vision_max_pages_per_doc: int = 60  # trần số trang gửi vision mỗi tài liệu (chi phí API)
    # Job 'pending' quá số phút này (Redis mất job) → sweeper enqueue lại một lần; quá thêm lần nữa → failed
    pending_job_requeue_after_min: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
