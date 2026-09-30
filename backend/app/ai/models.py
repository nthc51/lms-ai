from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class LLMCache(TimestampMixin, Base):
    """Cache câu trả lời LLM (spec 5.0). key_hash = sha256(provider, model, prompt, JSON schema)."""

    __tablename__ = "llm_cache"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    response: Mapped[str] = mapped_column(Text)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
