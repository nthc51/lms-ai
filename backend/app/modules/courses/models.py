import enum
import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin


class CourseStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class Course(IdMixin, TimestampMixin, Base):
    __tablename__ = "courses"

    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    cover_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[CourseStatus] = mapped_column(SAEnum(CourseStatus, name="course_status"),
                                                 default=CourseStatus.draft)

    sections: Mapped[list["Section"]] = relationship(
        back_populates="course", order_by="Section.position", passive_deletes=True)


class Section(IdMixin, TimestampMixin, Base):
    __tablename__ = "sections"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)

    course: Mapped[Course] = relationship(back_populates="sections")
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="section", order_by="Lesson.position", passive_deletes=True)


class Lesson(IdMixin, TimestampMixin, Base):
    __tablename__ = "lessons"

    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    content_md: Mapped[str] = mapped_column(Text, default="")
    duration_sec: Mapped[int | None] = mapped_column(Integer)

    section: Mapped[Section] = relationship(back_populates="lessons")
