import uuid

from app.core.security import hash_password
from app.core.time import utcnow
from app.modules.auth.models import Role, TeacherStatus, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.materials.models import Asset, AssetKind, Chunk, Source, SourceStatus, SourceType
from tests.fakes import InMemoryStorage


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


async def make_pdf_source(
    db, storage, owner: User, lesson: Lesson, pdf_bytes: bytes, status: SourceStatus = SourceStatus.pending
) -> Source:
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
    source = Source(lesson_id=lesson.id, asset_id=asset.id, type=SourceType.pdf, status=status)
    db.add(source)
    await db.commit()
    return source


def unit_vector(index: int, dim: int = 768) -> list[float]:
    v = [0.0] * dim
    v[index] = 1.0
    return v


async def add_chunk(
    db,
    source: Source,
    course: Course,
    lesson: Lesson,
    content: str,
    embedding: list[float],
    *,
    embedding_model: str = "fake-768",
    page_no: int | None = 1,
    heading_path: str = "",
    token_count: int | None = None,
    start_sec: float | None = None,
) -> Chunk:
    chunk = Chunk(
        source_id=source.id,
        course_id=course.id,
        lesson_id=lesson.id,
        content=content,
        heading_path=heading_path,
        page_no=page_no,
        start_sec=start_sec,
        token_count=len(content.split()) if token_count is None else token_count,
        embedding_model=embedding_model,
        embedding=embedding,
    )
    db.add(chunk)
    await db.commit()
    return chunk


BINARY_SEARCH = "Tìm kiếm nhị phân chia đôi khoảng tìm kiếm trên mảng đã sắp xếp."
# ~170 từ ≈ 240 token: đủ ngưỡng 150 token để sinh câu hỏi (spec 5.4 bước 2)
LONG_LESSON_TEXT = (
    "Tìm kiếm nhị phân là thuật toán tìm một giá trị trong mảng đã sắp xếp. "
    "Mỗi bước so sánh giá trị cần tìm với phần tử ở giữa khoảng đang xét, "
    "rồi loại bỏ một nửa khoảng không thể chứa giá trị đó. "
) * 4


async def seed_chunks(
    db,
    lesson_id: uuid.UUID,
    contents: list[str],
    *,
    heading_paths: list[str] | None = None,
    status: SourceStatus = SourceStatus.ready,
) -> list[Chunk]:
    """Gắn một source (mặc định ready) vào bài học rồi thêm chunk có embedding của FakeEmbedder(768) — cùng
    model 'fake-768' mà API dùng trong test. token_count tính như pipeline thật; chunk thứ i ở trang i + 1."""
    from app.ai.embedder import FakeEmbedder
    from app.ingestion.chunker import count_tokens

    lesson = await db.get(Lesson, lesson_id)
    section = await db.get(Section, lesson.section_id)
    course = await db.get(Course, section.course_id)
    owner = await db.get(User, course.teacher_id)
    source = await make_pdf_source(db, InMemoryStorage(), owner, lesson, b"%PDF-1.7", status=status)
    vectors = await FakeEmbedder(768).embed_documents(contents)
    chunks = []
    for i, (content, vector) in enumerate(zip(contents, vectors, strict=True)):
        chunks.append(
            await add_chunk(
                db,
                source,
                course,
                lesson,
                content,
                vector,
                page_no=i + 1,
                heading_path=heading_paths[i] if heading_paths else "",
                token_count=count_tokens(content),
            )
        )
    return chunks
