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
    vision_concurrency: int = 4  # số lời gọi vision chạy song song tối đa trong một tài liệu
    # Job 'pending' quá số phút này (Redis mất job) → sweeper enqueue lại một lần; quá thêm lần nữa → failed
    pending_job_requeue_after_min: int = 10
    llm_provider: str = "fake"  # fake | gemini
    llm_model: str = "gemini-2.5-flash"
    llm_cheap_model: str = "gemini-2.5-flash-lite"  # lời gọi rẻ: viết lại câu hỏi (spec 5.3 bước 1)
    llm_timeout_s: float = 60.0  # lời gọi thường (sinh quiz, tự kiểm tra)
    llm_stream_timeout_s: float = 120.0  # stream câu trả lời của Tutor
    llm_rewrite_timeout_s: float = 15.0
    llm_cache_enabled: bool = True
    # Chốt chặn Tutor (spec 5.3 bước 3): similarity cao nhất < τ thì từ chối, không gọi LLM.
    # Giá trị tạm, sẽ chọn lại trên tập dev ở tuần 3 (spec 9.2).
    tutor_refuse_threshold: float = 0.3
    tutor_top_k: int = 6
    tutor_rate_limit_per_hour: int = 30  # số câu hỏi Tutor mỗi học viên mỗi giờ (spec 5.3 bước 7)
    # Hạn chót tổng của bước viết lại câu hỏi (gồm cả retry); quá hạn thì dùng câu hỏi gốc.
    tutor_rewrite_deadline_s: float = 20.0
    # Hạn chót tổng trước token đầu tiên: viết lại + tìm tài liệu + mở stream (gồm retry). Quá hạn → event error.
    tutor_prestream_deadline_s: float = 60.0

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
