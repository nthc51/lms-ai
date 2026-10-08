import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.pagination import Page
from app.modules.auth.models import Role, TeacherStatus
from app.modules.courses.models import CourseStatus


def _strip(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _required(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Cần nhập lý do")
    return v


class ReasonIn(BaseModel):
    """Lý do bắt buộc (từ chối giảng viên, ẩn khóa học): người bị ảnh hưởng sẽ đọc được."""

    reason: str = Field(min_length=1, max_length=500)

    strip_reason = field_validator("reason")(_required)


class OptionalReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    strip_reason = field_validator("reason")(_strip)


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    teacher_status: TeacherStatus | None
    locked_at: datetime | None
    review_note: str | None
    email_verified: bool
    created_at: datetime
    course_count: int  # giảng viên: số khóa đang sở hữu
    enrollment_count: int  # học viên: số khóa đã đăng ký


class AdminUserPage(Page[AdminUserOut]):
    pass


class AdminCourseOut(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    status: CourseStatus
    teacher_id: uuid.UUID
    teacher_name: str
    teacher_email: str
    created_at: datetime
    lesson_count: int
    enrollment_count: int
    hidden_at: datetime | None
    hidden_reason: str | None


class AdminCoursePage(Page[AdminCourseOut]):
    pass


class DayCount(BaseModel):
    day: date
    count: int


class AdminStats(BaseModel):
    students: int
    teachers: int
    pending_teachers: int
    locked_users: int
    courses_published: int
    courses_draft: int
    courses_hidden: int
    enrollments: int
    tutor_questions_7d: int
    quiz_submissions_7d: int
    failed_jobs_7d: int
    tutor_downvotes_7d: int  # câu trả lời AI bị học viên bấm 👎 trong 7 ngày
    signups_14d: list[DayCount]  # đủ 14 ngày (giờ Việt Nam), ngày không có ai đăng ký = 0


class AdminActionOut(BaseModel):
    id: uuid.UUID
    admin_name: str | None  # None nếu tài khoản admin đã bị xóa
    action: str
    target_type: Literal["user", "course"]
    target_id: uuid.UUID
    target_label: str
    note: str | None
    created_at: datetime


class AdminActionPage(Page[AdminActionOut]):
    pass
