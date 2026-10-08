import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.pagination import Page
from app.modules.studio.models import ArtifactKind, StudioStatus


class GuideOut(BaseModel):
    status: StudioStatus
    title: str
    summary: str
    topics: list[str]
    questions: list[str]


class DocumentOut(BaseModel):
    """Một tài liệu PDF đã xử lý xong của bài, kèm hướng dẫn (S1). guide=None: chưa có (đang chờ sinh)."""

    source_id: uuid.UUID
    title: str  # tên AI suy ra; chưa có thì "Tài liệu N"
    page_count: int
    guide: GuideOut | None


class FileUrlOut(BaseModel):
    url: str


class ChunkOut(BaseModel):
    """Toàn văn một đoạn tài liệu, để xem trước nguồn [n] (S5)."""

    id: uuid.UUID
    source_id: uuid.UUID
    lesson_id: uuid.UUID
    lesson_title: str
    heading_path: str
    page_no: int | None
    start_sec: float | None
    content: str


class StudioItem(BaseModel):
    kind: ArtifactKind
    # none: chưa sinh lần nào; generating: đang sinh; ready: có bản dùng được; failed: lần sinh gần nhất lỗi
    status: Literal["none", "generating", "ready", "failed"]
    artifact_id: uuid.UUID | None  # bản dùng được mới nhất (có thể có cả khi status=generating/failed)
    job_id: uuid.UUID | None  # job đang chạy (status=generating)
    error: str | None
    stale: bool  # tài liệu đã đổi sau khi sinh bản này (và bản này chưa được giảng viên duyệt)
    reviewed: bool  # giảng viên đã sửa / duyệt
    created_at: datetime | None


class StudioOverview(BaseModel):
    has_content: bool  # phạm vi có tài liệu đã xử lý xong (không thì không sinh được gì)
    can_regenerate: bool  # người xem là chủ khóa / admin: được "Sinh lại" và sửa
    items: list[StudioItem]


class StudioRequestIn(BaseModel):
    course_id: uuid.UUID
    lesson_id: uuid.UUID | None = None
    force: bool = False  # chỉ chủ khóa / admin: sinh lại dù bản hiện tại còn mới


class StudioRequestOut(BaseModel):
    artifact_id: uuid.UUID
    status: StudioStatus
    job_id: uuid.UUID | None


class Card(BaseModel):
    front: str = Field(min_length=1, max_length=300)
    back: str = Field(min_length=1, max_length=800)
    sources: list[int] = Field(default_factory=list)


class ArtifactOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    lesson_id: uuid.UUID | None
    kind: ArtifactKind
    status: StudioStatus
    content_md: str
    cards: list[Card] | None
    citations: list[dict]
    error_msg: str | None
    stale: bool
    reviewed: bool
    created_at: datetime
    known_cards: list[int]  # flashcard: các thẻ người xem đã đánh dấu "Nhớ"


class ArtifactUpdate(BaseModel):
    """Giảng viên sửa nội dung: báo cáo sửa content_md, flashcard sửa cards. Sửa xong là bản đã duyệt."""

    content_md: str | None = Field(default=None, max_length=100_000)
    cards: list[Card] | None = Field(default=None, max_length=100)


class CardReviewIn(BaseModel):
    known: bool


class FollowupsOut(BaseModel):
    questions: list[str]


# ---------- ghi chú ----------


def _title(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    if not v:
        raise ValueError("Cần nhập tiêu đề")
    return v


class NoteIn(BaseModel):
    course_id: uuid.UUID
    lesson_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    content_md: str = Field(default="", max_length=50_000)
    # nguồn [n] đi kèm nội dung (vd. lưu một báo cáo Studio vào ghi chú); ghi chú riêng nên không cần kiểm
    citations: list[dict] = Field(default_factory=list, max_length=200)

    clean_title = field_validator("title")(_title)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_md: str | None = Field(default=None, max_length=50_000)

    clean_title = field_validator("title")(_title)


class NoteFromMessageIn(BaseModel):
    message_id: uuid.UUID


class NotesSynthesizeIn(BaseModel):
    note_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    title: str | None = Field(default=None, max_length=200)


class NoteOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    lesson_id: uuid.UUID | None
    title: str
    content_md: str
    citations: list[dict]
    status: StudioStatus
    from_message_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class NotePage(Page[NoteOut]):
    pass


class NoteSynthOut(BaseModel):
    note: NoteOut
    job_id: uuid.UUID
