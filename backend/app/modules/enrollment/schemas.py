import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.enrollment.models import ProgressStatus


class EnrollmentOut(BaseModel):
    course_id: uuid.UUID
    enrolled_at: datetime


class MyCourseOut(BaseModel):
    course_id: uuid.UUID
    title: str
    slug: str
    enrolled_at: datetime
    completed_at: datetime | None
    total_lessons: int
    done_lessons: int
    progress_pct: int


class ProgressIn(BaseModel):
    status: Literal["in_progress", "done"]
    video_position_sec: int = Field(ge=0)


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: ProgressStatus
    video_position_sec: int
    completed_at: datetime | None


class LessonDetail(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    course_id: uuid.UUID
    title: str
    content_md: str
    duration_sec: int | None
    progress: ProgressOut | None
