import uuid
from datetime import datetime

from pydantic import BaseModel


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
