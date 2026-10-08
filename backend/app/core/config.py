import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Provider AI hợp lệ. Gõ sai (vd "gemni") thì app/worker không khởi động thay vì âm thầm chạy bản giả.
AIProvider = Literal["fake", "gemini"]


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

    embed_provider: AIProvider = "fake"
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768
    vision_provider: AIProvider = "fake"
    vision_model: str = "gemini-3.5-flash"
    gemini_api_key: str = ""
    embed_timeout_s: float = 30.0
    # Số đoạn tối đa mỗi request embedding.
    embed_batch_size: int = 100
    # > 0: giới hạn token gửi embedding trong mỗi 60 giây (gói miễn phí Gemini: 30K TPM → đặt 25000).
    # 0 = không giới hạn. Lô cũng bị cắt nhỏ để không lô nào vượt giới hạn này.
    embed_tpm_limit: int = 0
    vision_timeout_s: float = 120.0
    vision_max_pages_per_doc: int = 60  # trần số trang gửi vision mỗi tài liệu (chi phí API)
    vision_concurrency: int = 4  # số lời gọi vision chạy song song tối đa trong một tài liệu
    # Job 'pending' quá số phút này (Redis mất job) → sweeper enqueue lại một lần; quá thêm lần nữa → failed
    pending_job_requeue_after_min: int = 10
    llm_provider: AIProvider = "fake"
    llm_model: str = "gemini-3.5-flash"
    llm_cheap_model: str = "gemini-3.5-flash-lite"  # lời gọi rẻ: viết lại câu hỏi (spec 5.3 bước 1)
    llm_timeout_s: float = 60.0  # lời gọi thường (sinh quiz, tự kiểm tra)
    llm_stream_timeout_s: float = 120.0  # stream câu trả lời của Tutor
    llm_rewrite_timeout_s: float = 15.0
    llm_cache_enabled: bool = True
    ai_usage_log_enabled: bool = True  # ghi mỗi lời gọi LLM vào bảng ai_calls (token theo loại việc)
    # Chốt chặn Tutor (spec 5.3 bước 3): similarity cao nhất < τ thì từ chối, không gọi LLM.
    # Giá trị tạm, sẽ chọn lại trên tập dev ở tuần 3 (spec 9.2).
    tutor_refuse_threshold: float = 0.3
    tutor_top_k: int = 6
    tutor_rate_limit_per_hour: int = 30  # số câu hỏi Tutor mỗi học viên mỗi giờ (spec 5.3 bước 7)
    # Đếm cả lần sai mật khẩu. Rộng tay vì cả lớp dùng chung một IP khi ở WiFi trường (NAT)
    login_rate_limit_per_min: int = 20
    # Hạn chót tổng của bước viết lại câu hỏi (gồm cả retry); quá hạn thì dùng câu hỏi gốc.
    tutor_rewrite_deadline_s: float = 20.0
    # Hạn chót tổng trước token đầu tiên: viết lại + tìm tài liệu + mở stream (gồm retry). Quá hạn → event error.
    tutor_prestream_deadline_s: float = 60.0
    # Địa chỉ frontend, dùng để tạo link trong email (xác nhận email...). Không có dấu / ở cuối.
    app_base_url: str = "http://localhost:3000"
    # Bắt buộc bấm link xác nhận email trước khi đăng nhập được.
    email_verification_required: bool = True
    verify_token_hours: int = 24
    # SMTP. Mặc định trỏ vào Mailpit (docker compose) để dev không gửi mail thật; chạy thật thì dùng Brevo.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False  # Brevo cổng 587: true
    smtp_timeout_s: float = 20.0
    mail_from: str = "LMS-AI <no-reply@example.com>"
    mail_max_attempts: int = 5  # gửi lỗi quá số lần này thì bỏ (status failed)

    # AI Studio (đề cương, FAQ, flashcard...): tổng token tài liệu gửi trong MỘT lời gọi. Tài liệu dài hơn thì
    # tóm tắt từng phần trước (map) rồi gộp (reduce).
    studio_max_input_tokens: int = 12000
    studio_rate_limit_per_hour: int = 10  # số lần một học viên được yêu cầu sinh mới mỗi giờ
    source_guide_max_input_tokens: int = 6000  # hướng dẫn tài liệu: chỉ đọc phần đầu mỗi mục tới mức này
    # Kích thước đoạn khi chia tài liệu (benchmark dùng để so cấu hình). Đổi thì phải xử lý lại tài liệu.
    chunk_max_tokens: int = 700
    chunk_overlap_tokens: int = 100

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _require_gemini_key(self) -> "Settings":
        """Provider nào là gemini thì phải có GEMINI_API_KEY ngay lúc khởi động (không đợi tới lời gọi đầu tiên)."""
        using = [
            name
            for name, value in (
                ("LLM_PROVIDER", self.llm_provider),
                ("EMBED_PROVIDER", self.embed_provider),
                ("VISION_PROVIDER", self.vision_provider),
            )
            if value == "gemini"
        ]
        if using and not self.gemini_api_key.strip():
            raise ValueError(f"GEMINI_API_KEY trống trong khi {', '.join(using)}=gemini")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
