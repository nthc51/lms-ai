import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.courses.models import CourseStatus


class CourseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=5000)


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    title: str
    slug: str
    description: str
    status: CourseStatus
    created_at: datetime
