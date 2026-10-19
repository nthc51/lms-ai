import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.pagination import Page

MAX_BODY = 2000


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)
    parent_id: uuid.UUID | None = None  # trả lời bình luận gốc nào (bỏ trống = hỏi mới)

    @field_validator("body")
    @classmethod
    def strip_body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nội dung không được để trống")
        return v


class CommentOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    body: str | None  # None khi đã xóa
    deleted: bool
    author_name: str
    author_role: Literal["student", "teacher", "admin"]
    is_course_teacher: bool  # người viết là giảng viên của khóa: hiện nhãn "Giảng viên"
    can_delete: bool  # người xem hiện tại xóa được (tác giả, giảng viên khóa, admin)
    created_at: datetime
    replies: list["CommentOut"] = []


class CommentPage(Page[CommentOut]):
    pass
