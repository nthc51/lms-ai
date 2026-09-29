import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


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
