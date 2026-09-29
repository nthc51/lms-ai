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


class SectionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SectionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    position: int


class LessonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content_md: str = Field(default="", max_length=100_000)


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_md: str | None = Field(default=None, max_length=100_000)
    duration_sec: int | None = Field(default=None, ge=0)


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID
    title: str
    position: int
    content_md: str
    duration_sec: int | None


class ReorderSection(BaseModel):
    id: uuid.UUID
    lesson_ids: list[uuid.UUID]


class ReorderIn(BaseModel):
    sections: list[ReorderSection]
