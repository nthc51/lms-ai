import uuid

from app.core.security import hash_password
from app.core.time import utcnow
from app.modules.auth.models import Role, TeacherStatus, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.materials.models import Asset, AssetKind, Chunk, Source, SourceType


async def make_user(db, role: Role = Role.teacher) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@x.com",
        password_hash=hash_password("password123"),
        full_name="Người dùng",
        role=role,
        teacher_status=TeacherStatus.approved if role == Role.teacher else None,
    )
    db.add(user)
    await db.commit()
    return user


async def make_lesson(db, teacher: User) -> tuple[Course, Lesson]:
    course = Course(
        teacher_id=teacher.id,
        title="Khóa test",
        slug=f"khoa-{uuid.uuid4().hex[:6]}",
        status=CourseStatus.published,
    )
    db.add(course)
    await db.flush()
    section = Section(course_id=course.id, title="Chương 1", position=1)
    db.add(section)
    await db.flush()
    lesson = Lesson(section_id=section.id, title="Bài 1", position=1)
    db.add(lesson)
    await db.commit()
    return course, lesson


async def make_pdf_source(db, storage, owner: User, lesson: Lesson, pdf_bytes: bytes) -> Source:
    key = f"pdf/{owner.id}/{uuid.uuid4().hex}.pdf"
    await storage.put(key, pdf_bytes, "application/pdf")
    asset = Asset(
        owner_id=owner.id,
        kind=AssetKind.pdf,
        storage_key=key,
        mime="application/pdf",
        size_bytes=len(pdf_bytes),
        verified_at=utcnow(),
    )
    db.add(asset)
    await db.flush()
    source = Source(lesson_id=lesson.id, asset_id=asset.id, type=SourceType.pdf)
    db.add(source)
    await db.commit()
    return source


def unit_vector(index: int, dim: int = 768) -> list[float]:
    v = [0.0] * dim
    v[index] = 1.0
    return v


async def add_chunk(
    db, source: Source, course: Course, lesson: Lesson, content: str, embedding: list[float]
) -> Chunk:
    chunk = Chunk(
        source_id=source.id,
        course_id=course.id,
        lesson_id=lesson.id,
        content=content,
        heading_path="",
        page_no=1,
        token_count=len(content.split()),
        embedding_model="fake-768",
        embedding=embedding,
    )
    db.add(chunk)
    await db.commit()
    return chunk
