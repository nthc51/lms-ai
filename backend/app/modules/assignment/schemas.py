import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.pagination import Page
from app.modules.assignment.models import AssignmentStatus, SubmissionStatus

MAX_CRITERIA = 8
MAX_TEXT = 20_000  # ký tự bài làm gõ trực tiếp
MAX_FEEDBACK = 5_000


def _strip_required(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Không được để trống")
    return v


class RubricItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str = Field(min_length=1, max_length=200)  # tên tiêu chí
    max_points: int = Field(ge=1, le=100)
    description: str = Field("", max_length=1000)  # thế nào là đạt điểm tối đa

    @field_validator("criterion")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _strip_required(v)


class RubricItem(BaseModel):
    key: str  # c1, c2, ... (server đặt theo thứ tự)
    criterion: str
    max_points: int
    description: str


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=20_000)
    due_at: AwareDatetime | None = None
    rubric: list[RubricItemIn] = Field(min_length=1, max_length=MAX_CRITERIA)

    @field_validator("title", "instructions")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _strip_required(v)


class AssignmentUpdate(BaseModel):
    """Trường không gửi thì giữ nguyên; `due_at: null` tường minh = bỏ hạn nộp. Rubric chỉ đổi được khi chưa có
    bài nộp nào."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=200)
    instructions: str | None = Field(None, min_length=1, max_length=20_000)
    due_at: AwareDatetime | None = None
    rubric: list[RubricItemIn] | None = Field(None, min_length=1, max_length=MAX_CRITERIA)

    @field_validator("title", "instructions")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return None if v is None else _strip_required(v)


class FileRef(BaseModel):
    asset_id: uuid.UUID
    name: str | None


class MySubmission(BaseModel):
    """Bài nộp của chính học viên. Điểm và nhận xét chỉ có sau khi giảng viên xác nhận; học viên không thấy điểm AI."""

    id: uuid.UUID
    version: int
    status: SubmissionStatus
    submitted_at: datetime
    text_content: str
    file: FileRef | None
    final_scores: dict[str, float] | None
    final_total: float | None
    teacher_feedback: str | None
    graded_at: datetime | None


class AssignmentOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    lesson_title: str
    course_slug: str  # để dựng link về bài học (/learn/<slug>/<lesson_id>)
    title: str
    instructions: str
    due_at: datetime | None
    rubric: list[RubricItem]
    max_total: int
    status: AssignmentStatus
    created_at: datetime
    # chỉ giảng viên của khóa / admin
    submission_count: int | None = None
    to_review: int | None = None  # bài AI đã gợi ý hoặc AI lỗi, chờ giảng viên xác nhận
    # chỉ học viên
    my_submission: MySubmission | None = None


class AssignmentPage(Page[AssignmentOut]):
    pass


class SubmissionIn(BaseModel):
    """Gõ bài làm, đính kèm một file (PDF hoặc .txt, upload với kind=submission), hoặc cả hai."""

    model_config = ConfigDict(extra="forbid")

    text_content: str = Field("", max_length=MAX_TEXT)
    asset_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> "SubmissionIn":
        self.text_content = self.text_content.strip()
        if not self.text_content and self.asset_id is None:
            raise ValueError("Bài làm trống: hãy gõ nội dung hoặc đính kèm file")
        return self


class CriterionResult(BaseModel):
    score: float
    justification: str
    evidence_quote: str
    evidence_found: bool  # câu trích có thật trong bài làm (so khớp gần đúng)


class AIResult(BaseModel):
    scores: dict[str, CriterionResult]
    feedback: str
    total: float
    model: str
    prompt_version: str
    version: int  # bài nộp version nào được chấm


class SubmissionListItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    student_name: str
    status: SubmissionStatus
    version: int
    submitted_at: datetime
    ai_total: float | None
    final_total: float | None
    flagged: int  # số tiêu chí AI trích dẫn không tìm thấy trong bài làm


class SubmissionPage(Page[SubmissionListItem]):
    pass


class SubmissionDetail(BaseModel):
    """Bài nộp cho giảng viên chấm: bài làm, file, gợi ý của AI và điểm đã xác nhận (nếu có)."""

    id: uuid.UUID
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    student_name: str
    status: SubmissionStatus
    version: int
    submitted_at: datetime
    text_content: str
    file: FileRef | None
    file_url: str | None  # link xem file (hết hạn sau 1 giờ)
    ai_result: AIResult | None
    ai_error: str | None
    final_scores: dict[str, float] | None
    final_total: float | None
    teacher_feedback: str | None
    graded_at: datetime | None


class GradeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(
        ge=1
    )  # version của bài giảng viên đang xem; lệch với bản mới nhất → 409 STALE_VERSION
    scores: dict[str, float]  # đủ mọi tiêu chí của rubric, mỗi điểm trong 0..max_points
    feedback: str | None = Field(None, max_length=MAX_FEEDBACK)
