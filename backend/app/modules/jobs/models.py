import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin

ACTIVE_JOB_PREDICATE = "status IN ('pending', 'processing')"


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class Job(IdMixin, TimestampMixin, Base):
    """type quyết định ref_id trỏ tới đâu: ingest_pdf/ingest_video → sources.id, quiz_gen → lessons.id,
    grade_submission → submissions.id (ref_version = submissions.version)."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("uq_active_job", "type", "ref_id", "ref_version", unique=True,
              postgresql_where=text(ACTIVE_JOB_PREDICATE)),
    )

    type: Mapped[str] = mapped_column(String(50))
    ref_id: Mapped[uuid.UUID] = mapped_column()
    ref_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, name="job_status"), default=JobStatus.pending)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
