import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.db import Base, IdMixin, TimestampMixin

EMBED_DIM = get_settings().embed_dim


class AssetKind(str, enum.Enum):
    pdf = "pdf"
    video = "video"
    submission = "submission"
    certificate = "certificate"
    image = "image"


class Asset(IdMixin, TimestampMixin, Base):
    __tablename__ = "assets"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[AssetKind] = mapped_column(SAEnum(AssetKind, name="asset_kind"))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceType(str, enum.Enum):
    pdf = "pdf"
    video = "video"


class SourceStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ExtractionMethod(str, enum.Enum):
    text = "text"
    vision = "vision"


class Source(IdMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    # Một file chỉ gắn một lần vào mỗi bài học (gắn lại thì 409 ALREADY_ATTACHED)
    __table_args__ = (UniqueConstraint("lesson_id", "asset_id", name="uq_sources_lesson_asset"),)

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    type: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type"))
    status: Mapped[SourceStatus] = mapped_column(SAEnum(SourceStatus, name="source_status"),
                                                 default=SourceStatus.pending)
    error_msg: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourcePage(Base):
    __tablename__ = "source_pages"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    page_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(SAEnum(ExtractionMethod, name="extraction_method"))
    markdown: Mapped[str] = mapped_column(Text)


class Chunk(IdMixin, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_scope", "course_id", "lesson_id", "embedding_model"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    heading_path: Mapped[str] = mapped_column(String(500), default="")
    page_no: Mapped[int | None] = mapped_column(Integer)
    start_sec: Mapped[float | None] = mapped_column(Float)
    end_sec: Mapped[float | None] = mapped_column(Float)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding_model: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, immutable_unaccent(coalesce(content, '')))", persisted=True),
    )
