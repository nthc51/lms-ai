import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import Page
from app.modules.tutor.models import ChatRole


class SessionCreate(BaseModel):
    course_id: uuid.UUID
    lesson_id: uuid.UUID | None = None  # None = hỏi trên toàn khóa


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    lesson_id: uuid.UUID | None
    created_at: datetime


class SessionPage(Page[SessionOut]):
    pass


class Citation(BaseModel):
    n: int
    chunk_id: uuid.UUID
    lesson_id: uuid.UUID
    page_no: int | None
    start_sec: float | None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: ChatRole
    content: str
    citations: list[Citation]
    refused: bool
    truncated: bool
    feedback: int | None
    created_at: datetime


class MessagePage(Page[MessageOut]):
    pass


class AskIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=2000)


class FeedbackIn(BaseModel):
    value: Literal[1, -1] | None  # None = bỏ đánh giá


class AvailabilityOut(BaseModel):
    available: bool
    ready_chunks: int
    message: str | None  # "Tài liệu đang được xử lý" khi chưa có chunk nào (spec 5.7)
