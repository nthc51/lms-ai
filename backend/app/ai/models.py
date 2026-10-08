from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class LLMCache(TimestampMixin, Base):
    """Cache câu trả lời LLM (spec 5.0). key_hash = sha256(provider, model, prompt, JSON schema)."""

    __tablename__ = "llm_cache"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    response: Mapped[str] = mapped_column(Text)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class AiCall(IdMixin, TimestampMixin, Base):
    """Nhật ký mỗi lời gọi LLM (kể cả cache hit): đếm token theo loại việc cho trang admin và benchmark.
    Ghi best-effort bởi LLMClient; tắt bằng AI_USAGE_LOG_ENABLED=false."""

    __tablename__ = "ai_calls"
    __table_args__ = (Index("ix_ai_calls_created", "created_at"),)

    op: Mapped[str] = mapped_column(String(50))  # tutor_answer | quiz_generate | studio_study_guide | ...
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))  # ok | incomplete | empty_output | invalid_output | ...
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
