"""Xử lý lại các tài liệu PDF đã tải lên (như bấm "Xử lý lại" cho từng tài liệu).

Khi nào cần: sau khi sửa cách trích chữ (ví dụ chèn lại dấu cách bị mất ở PDF xuất từ slide), tài liệu cũ vẫn giữ
đoạn trích theo cách cũ cho tới khi được xử lý lại. Chỉ xử lý tài liệu đang "ready" hoặc "failed"; tài liệu đang chờ
/ đang xử lý thì bỏ qua.

Lưu ý chi phí: khi dùng AI thật, mỗi tài liệu gọi lại vision (tối đa VISION_MAX_PAGES_PER_DOC trang) và embedding.

Chạy từ thư mục backend/ (Docker đang chạy, worker đang chạy):
    uv run python -m scripts.reprocess_pdfs                    # chỉ liệt kê, không làm gì
    uv run python -m scripts.reprocess_pdfs --yes              # xử lý lại tất cả
    uv run python -m scripts.reprocess_pdfs --course kttt-8feb7f --yes   # chỉ một khóa (slug trên URL)
"""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models_registry  # noqa: F401 — nạp mọi model (khóa ngoại)
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.courses.models import Course, Lesson, Section
from app.modules.jobs.queue import ArqQueue, JobQueue
from app.modules.jobs.service import create_job
from app.modules.materials.models import Source, SourceStatus, SourceType
from app.modules.materials.sources import INGEST_PDF


async def find_sources(session_factory: async_sessionmaker, course_slug: str | None) -> list[tuple]:
    stmt = (
        select(Source.id, Source.status, Course.slug, Lesson.title)
        .join(Lesson, Lesson.id == Source.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(Source.type == SourceType.pdf)
        .order_by(Course.slug, Lesson.title, Source.id)
    )
    if course_slug:
        stmt = stmt.where(Course.slug == course_slug)
    async with session_factory() as db:
        return list((await db.execute(stmt)).all())


async def reprocess(
    session_factory: async_sessionmaker, queue: JobQueue, course_slug: str | None = None
) -> tuple[int, int]:
    """Trả về (số tài liệu đã xếp hàng xử lý lại, số bỏ qua vì đang chờ / đang xử lý)."""
    queued = skipped = 0
    for source_id, status, _, _ in await find_sources(session_factory, course_slug):
        if status not in (SourceStatus.ready, SourceStatus.failed):
            skipped += 1
            continue
        async with session_factory() as db:
            job, created = await create_job(db, INGEST_PDF, source_id, created_by=None)
            if not created:
                await db.rollback()
                skipped += 1
                continue
            source = await db.get(Source, source_id)
            source.status = SourceStatus.pending
            source.error_msg = None
            await db.commit()
        await queue.enqueue(job)  # chỉ sau khi job đã commit
        queued += 1
    return queued, skipped


async def main(course: str | None, yes: bool) -> None:
    rows = await find_sources(SessionLocal, course)
    for _, status, slug, title in rows:
        print(f"  [{status.value:10}] {slug} / {title}")
    if not yes:
        print(f"{len(rows)} tài liệu. Thêm --yes để xử lý lại.")
        return
    queued, skipped = await reprocess(SessionLocal, ArqQueue(get_settings().redis_url), course)
    print(f"Đã xếp hàng xử lý lại {queued} tài liệu, bỏ qua {skipped} (đang chờ / đang xử lý).")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--course", help="slug của khóa học (phần sau /teach/ trên URL)")
    p.add_argument("--yes", action="store_true", help="thực hiện (mặc định chỉ liệt kê)")
    a = p.parse_args()
    asyncio.run(main(a.course, a.yes))
