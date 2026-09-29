import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.materials.models import AssetKind, ExtractionMethod, SourceStatus, SourceType


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


class SourceCreate(BaseModel):
    asset_id: uuid.UUID


class SourceOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    type: SourceType
    status: SourceStatus
    error_msg: str | None  # failed: lý do lỗi; ready: có thể là cảnh báo (vượt trần trang vision)
    warning: str | None  # = error_msg khi status == ready, ngược lại None
    processed_at: datetime | None
    page_count: int
    vision_pages: int  # số trang trích bằng vision (source_pages.extraction_method = 'vision')
    chunk_count: int


class SourceCreated(BaseModel):
    source: SourceOut
    job_id: uuid.UUID


class JobRef(BaseModel):
    job_id: uuid.UUID


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_no: int
    extraction_method: ExtractionMethod
    markdown: str
