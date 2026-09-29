import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.materials.models import AssetKind


class PresignIn(BaseModel):
    kind: Literal["pdf", "video", "submission", "image"]
    mime: str = Field(max_length=100)
    size: int = Field(gt=0)


class PresignOut(BaseModel):
    asset_id: uuid.UUID
    put_url: str


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: AssetKind
    mime: str
    size_bytes: int
    verified_at: datetime | None


class UrlOut(BaseModel):
    url: str
