import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import Page
from app.modules.tutor.models import ChatRole


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    # Câu hỏi gửi lúc tài liệu đang xử lý, chưa có câu trả lời (worker trả lời khi xử lý xong)
    waiting_for_docs: bool = False
    created_at: datetime


class MessagePage(Page[MessageOut]):
    pass


class AskIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    content: str = Field(min_length=1, max_length=2000)


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Literal[1, -1] | None  # None = bỏ đánh giá


# ready: hỏi được ngay. processing: chưa có chunk nào nhưng còn tài liệu đang xử lý (gửi câu hỏi chờ được).
# model_mismatch: tài liệu đã xử lý bằng model embedding khác model hiện tại (đổi provider/model).
# failed: tài liệu xử lý lỗi. empty: chưa có tài liệu (hoặc tài liệu không có chữ). draft: hỏi cả khóa khi khóa
# còn nháp.
TutorState = Literal["ready", "processing", "model_mismatch", "failed", "empty", "draft"]


class AvailabilityOut(BaseModel):
    available: bool
    ready_chunks: int
    message: str | None  # lý do chưa hỏi được (None khi available)
    state: TutorState
    processing_docs: int  # số tài liệu đang chờ / đang xử lý trong phạm vi
    can_queue: bool  # gửi câu hỏi chờ được (POST /tutor/sessions/{id}/questions)
