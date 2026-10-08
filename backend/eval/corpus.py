"""Nạp tài liệu benchmark vào DB như một khóa học thật (đúng pipeline xử lý PDF), dùng lại nếu đã nạp.

Mỗi (file PDF, kích thước đoạn, model embedding) là một khóa "[Benchmark] ..." riêng, slug
eval-<sha12>-c<chunk>-<model>. Chạy lại benchmark không xử lý lại tài liệu (không tốn quota vision/embedding)."""

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.retrieval import SearchScope
from app.ai.vision import VisionExtractor
from app.core.security import hash_password
from app.core.time import utcnow
from app.ingestion.pipeline import ingest_pdf_source
from app.modules.auth.models import Role, TeacherStatus, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.materials.models import Asset, AssetKind, Chunk, Source, SourceStatus, SourceType

BOT_EMAIL = "benchmark-bot@example.com"


class _BytesStorage:
    """Storage tối thiểu cho ingest_pdf_source: chỉ cần đọc lại file PDF."""

    def __init__(self, data: bytes):
        self._data = data

    async def read_all(self, key: str) -> bytes:
        return self._data


@dataclass(frozen=True)
class Corpus:
    scope: SearchScope
    course_title: str
    pdf_sha: str
    chunk_count: int


def corpus_slug(pdf_sha: str, chunk_max_tokens: int, embedding_model: str) -> str:
    model = re.sub(r"[^a-z0-9]+", "-", embedding_model.lower()).strip("-")
    return f"eval-{pdf_sha[:12]}-c{chunk_max_tokens}-{model}"[:240]


async def _bot(db) -> User:
    user = await db.scalar(select(User).where(User.email == BOT_EMAIL))
    if user is None:
        user = User(
            email=BOT_EMAIL,
            password_hash=hash_password(uuid.uuid4().hex),  # không ai đăng nhập được
            full_name="Benchmark",
            role=Role.teacher,
            teacher_status=TeacherStatus.approved,
            email_verified_at=utcnow(),
        )
        db.add(user)
        await db.flush()
    return user


async def prepare_corpus(
    pdf_path: str | Path,
    *,
    chunk_max_tokens: int,
    embedder: Embedder,
    vision: VisionExtractor,
    session_factory: async_sessionmaker,
) -> Corpus:
    data = Path(pdf_path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    slug = corpus_slug(sha, chunk_max_tokens, embedder.model)
    async with session_factory() as db:
        course = await db.scalar(select(Course).where(Course.slug == slug))
        if course is not None:
            lesson_id, n = (
                await db.execute(
                    select(Chunk.lesson_id, func.count())
                    .join(Source, Source.id == Chunk.source_id)
                    .where(Chunk.course_id == course.id, Source.status == SourceStatus.ready)
                    .group_by(Chunk.lesson_id)
                )
            ).one_or_none() or (None, 0)
            if lesson_id is not None and n:
                return Corpus(SearchScope(course.id, lesson_id), course.title, sha, n)
            raise RuntimeError(
                f"Khóa benchmark {slug} đã có nhưng chưa xử lý xong tài liệu: xóa khóa đó trong DB rồi chạy lại"
            )
        bot = await _bot(db)
        course = Course(
            teacher_id=bot.id,
            title=f"[Benchmark] {Path(pdf_path).stem}",
            slug=slug,
            status=CourseStatus.draft,  # nháp: không hiện ở /explore, không tính là khóa đã xuất bản
        )
        db.add(course)
        await db.flush()
        section = Section(course_id=course.id, title="Tài liệu", position=1)
        db.add(section)
        await db.flush()
        lesson = Lesson(section_id=section.id, title=Path(pdf_path).stem, position=1)
        asset = Asset(
            owner_id=bot.id,
            kind=AssetKind.pdf,
            storage_key=f"eval/{slug}.pdf",
            mime="application/pdf",
            size_bytes=len(data),
            verified_at=utcnow(),
        )
        db.add_all([lesson, asset])
        await db.flush()
        source = Source(lesson_id=lesson.id, asset_id=asset.id, type=SourceType.pdf)
        db.add(source)
        await db.commit()
        ids = (course.id, lesson.id, source.id, course.title)
    n = await ingest_pdf_source(
        ids[2],
        storage=_BytesStorage(data),
        embedder=embedder,
        vision=vision,
        session_factory=session_factory,
        chunk_max_tokens=chunk_max_tokens,
    )
    return Corpus(SearchScope(ids[0], ids[1]), ids[3], sha, n)
