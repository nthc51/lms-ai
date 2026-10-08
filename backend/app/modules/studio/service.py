"""AI Studio: tài liệu cho học viên (S1), xem trước nguồn (S5), báo cáo / flashcard (S2, S3), gợi ý hỏi tiếp (S5)."""

import logging
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import LLMClient
from app.ai.prompts import load_prompt
from app.core.config import get_settings
from app.core.errors import AppError, forbidden, not_found
from app.core.ratelimit import RateLimiter
from app.core.storage import Storage
from app.core.time import utcnow
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, Lesson
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.queue import JobQueue
from app.modules.jobs.service import create_and_enqueue
from app.modules.materials.models import Asset, Chunk, Source, SourcePage, SourceStatus, SourceType
from app.modules.studio.generation import cited_numbers, fingerprint, load_scope_chunks
from app.modules.studio.models import ArtifactKind, FlashcardReview, SourceGuide, StudioStatus, StudyArtifact
from app.modules.studio.schemas import (
    ArtifactOut,
    ArtifactUpdate,
    ChunkOut,
    DocumentOut,
    FollowupsOut,
    GuideOut,
    StudioItem,
    StudioOverview,
    StudioRequestIn,
    StudioRequestOut,
)
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from app.modules.tutor.service import ensure_course_access

logger = logging.getLogger(__name__)

STUDIO_JOB = "studio_gen"


def is_course_staff(course: Course, user: User) -> bool:
    return user.role == Role.admin or course.teacher_id == user.id


async def ensure_scope(
    db: AsyncSession, user: User, course_id: uuid.UUID, lesson_id: uuid.UUID | None
) -> Course:
    """Quyền như AI Tutor: chủ khóa / admin, hoặc học viên đã đăng ký khóa đã xuất bản. Bài phải thuộc khóa."""
    if lesson_id is None:
        return await ensure_course_access(db, course_id, user)
    _, course = await ensure_lesson_access(db, lesson_id, user)
    if course.id != course_id:
        raise not_found("Bài học")
    return course


# ---------- tài liệu (S1) và xem trước nguồn (S5) ----------


async def dead_generating(db: AsyncSession, job_type: str, ref_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Trong các hàng đang 'generating' (ref_ids), những hàng mà job gần nhất đã done / failed hoặc không còn:
    handler bị hủy (quá hạn, worker chết) nên không ghi được failed. Đọc coi như lỗi, giống _item."""
    if not ref_ids:
        return set()
    rows = await db.execute(
        select(Job.ref_id, Job.status)
        .where(Job.type == job_type, Job.ref_id.in_(ref_ids))
        .order_by(Job.created_at)
    )
    latest = {ref: status for ref, status in rows}  # job mới nhất ghi đè
    return {r for r in ref_ids if latest.get(r) in (None, JobStatus.failed, JobStatus.done)}


def _doc_title(guide_title: str | None, file_name: str | None, index: int) -> str:
    if guide_title:
        return guide_title
    if file_name:
        return file_name[:-4] if file_name.lower().endswith(".pdf") else file_name
    return f"Tài liệu {index}"


async def lesson_documents(db: AsyncSession, user: User, lesson_id: uuid.UUID) -> list[DocumentOut]:
    """Mọi PDF của bài, kể cả đang xử lý. Tài liệu xử lý lỗi chỉ giảng viên / admin thấy (để biết mà tải lại)."""
    _, course = await ensure_lesson_access(db, lesson_id, user)
    pages = select(SourcePage.source_id, func.count().label("n")).group_by(SourcePage.source_id).subquery()
    stmt = (
        select(Source.id, Source.status, Asset.original_name, func.coalesce(pages.c.n, 0), SourceGuide)
        .join(Asset, Asset.id == Source.asset_id)
        .outerjoin(pages, pages.c.source_id == Source.id)
        .outerjoin(SourceGuide, SourceGuide.source_id == Source.id)
        .where(Source.lesson_id == lesson_id, Source.type == SourceType.pdf)
        .order_by(Source.created_at, Source.id)
    )
    if not is_course_staff(course, user):
        stmt = stmt.where(Source.status != SourceStatus.failed)
    rows = (await db.execute(stmt)).all()
    dead = await dead_generating(
        db,
        "source_guide",
        [r[0] for r in rows if r[4] is not None and r[4].status == StudioStatus.generating],
    )
    out = []
    for i, (source_id, status, file_name, page_count, guide) in enumerate(rows, 1):
        out.append(
            DocumentOut(
                source_id=source_id,
                title=_doc_title(guide.title if guide is not None else None, file_name, i),
                file_name=file_name,
                status=status,
                page_count=page_count if status == SourceStatus.ready else 0,
                guide=None
                if guide is None
                else GuideOut(
                    status=StudioStatus.failed if source_id in dead else guide.status,
                    title=guide.title,
                    summary=guide.summary,
                    topics=guide.topics,
                    questions=guide.questions,
                ),
            )
        )
    return out


async def source_file_url(
    db: AsyncSession, storage: Storage, user: User, source_id: uuid.UUID, *, download: bool = False
) -> str:
    """URL ký sẵn (1 giờ) để xem PDF trong trình duyệt (frontend thêm #page=N để nhảy tới trang), hoặc tải về
    với tên file gốc. Không cần chờ AI xử lý xong: file đã được kiểm tra lúc tải lên."""
    row = (
        await db.execute(
            select(Source, Asset.storage_key, Asset.mime, Asset.original_name)
            .join(Asset, Asset.id == Source.asset_id)
            .where(Source.id == source_id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("Tài liệu")
    source, key, mime, file_name = row
    _, course = await ensure_lesson_access(db, source.lesson_id, user)
    if source.status == SourceStatus.failed and not is_course_staff(course, user):
        raise not_found("Tài liệu")
    name = None
    if download:
        name = file_name or "tai-lieu.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
    return await storage.presign_get(key, mime, download_name=name)


async def chunk_detail(db: AsyncSession, user: User, chunk_id: uuid.UUID) -> ChunkOut:
    row = (
        await db.execute(
            select(Chunk, Lesson.title).join(Lesson, Lesson.id == Chunk.lesson_id).where(Chunk.id == chunk_id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("Đoạn tài liệu")
    chunk, lesson_title = row
    await ensure_lesson_access(db, chunk.lesson_id, user)
    return ChunkOut(
        id=chunk.id,
        source_id=chunk.source_id,
        lesson_id=chunk.lesson_id,
        lesson_title=lesson_title,
        heading_path=chunk.heading_path,
        page_no=chunk.page_no,
        start_sec=chunk.start_sec,
        content=chunk.content,
    )


# ---------- báo cáo, flashcard (S2, S3) ----------


def _scope_filter(course_id: uuid.UUID, lesson_id: uuid.UUID | None):
    return (
        StudyArtifact.course_id == course_id,
        StudyArtifact.lesson_id == lesson_id if lesson_id is not None else StudyArtifact.lesson_id.is_(None),
    )


async def _latest_job(db: AsyncSession, artifact_id: uuid.UUID) -> Job | None:
    return await db.scalar(
        select(Job)
        .where(Job.type == STUDIO_JOB, Job.ref_id == artifact_id)
        .order_by(Job.created_at.desc())
        .limit(1)
    )


async def _item(db: AsyncSession, kind: ArtifactKind, artifacts: list[StudyArtifact], fp: str) -> StudioItem:
    """artifacts: mọi bản của phạm vi + loại này, mới nhất trước."""
    ready = next((a for a in artifacts if a.status == StudioStatus.ready), None)
    newest = artifacts[0] if artifacts else None
    status, job_id, error = ("ready" if ready else "none"), None, None
    if newest is not None and newest is not ready:
        job = await _latest_job(db, newest.id)
        if (
            newest.status == StudioStatus.generating
            and job is not None
            and job.status
            not in (
                JobStatus.failed,
                JobStatus.done,
            )
        ):
            status, job_id = "generating", job.id
        elif newest.status == StudioStatus.failed or newest.status == StudioStatus.generating:
            # generating mà job đã kết thúc (worker chết, quá hạn): coi như lỗi
            status, error = (
                "failed",
                newest.error_msg or (job.error_msg if job else None) or "Sinh nội dung bị gián đoạn",
            )
    return StudioItem(
        kind=kind,
        status=status,
        artifact_id=ready.id if ready else None,
        job_id=job_id,
        error=error,
        stale=bool(ready and ready.reviewed_at is None and ready.fingerprint != fp),
        reviewed=bool(ready and ready.reviewed_at is not None),
        created_at=ready.created_at if ready else None,
    )


async def overview(
    db: AsyncSession, user: User, course_id: uuid.UUID, lesson_id: uuid.UUID | None
) -> StudioOverview:
    course = await ensure_scope(db, user, course_id, lesson_id)
    chunks = await load_scope_chunks(db, course_id, lesson_id)
    fp = fingerprint(chunks)
    rows = (
        await db.scalars(
            select(StudyArtifact)
            .where(*_scope_filter(course_id, lesson_id))
            .order_by(StudyArtifact.created_at.desc(), StudyArtifact.id)
        )
    ).all()
    items = [await _item(db, kind, [a for a in rows if a.kind == kind], fp) for kind in ArtifactKind]
    return StudioOverview(has_content=bool(chunks), can_regenerate=is_course_staff(course, user), items=items)


async def request_artifact(
    db: AsyncSession,
    queue: JobQueue,
    limiter: RateLimiter,
    user: User,
    kind: ArtifactKind,
    data: StudioRequestIn,
) -> StudioRequestOut:
    """Trả bản dùng được nếu còn mới (hoặc đã được giảng viên duyệt); không thì tạo bản mới và job sinh nền.
    Khóa theo phạm vi (advisory lock) để hai người bấm cùng lúc chỉ tạo một job."""
    course = await ensure_scope(db, user, data.course_id, data.lesson_id)
    staff = is_course_staff(course, user)
    if data.force and not staff:
        raise forbidden("Chỉ giảng viên của khóa được sinh lại")
    key = f"studio:{data.course_id}:{data.lesson_id}:{kind.value}"
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(key))))
    chunks = await load_scope_chunks(db, data.course_id, data.lesson_id)
    if not chunks:
        raise AppError("NO_CONTENT", "Chưa có tài liệu nào được xử lý xong trong phạm vi này", 409)
    fp = fingerprint(chunks)
    artifacts = (
        await db.scalars(
            select(StudyArtifact)
            .where(*_scope_filter(data.course_id, data.lesson_id), StudyArtifact.kind == kind)
            .order_by(StudyArtifact.created_at.desc(), StudyArtifact.id)
        )
    ).all()
    item = await _item(db, kind, list(artifacts), fp)
    if item.status == "generating":
        return StudioRequestOut(
            artifact_id=artifacts[0].id, status=StudioStatus.generating, job_id=item.job_id
        )
    if item.artifact_id is not None and not item.stale and not data.force:
        return StudioRequestOut(artifact_id=item.artifact_id, status=StudioStatus.ready, job_id=None)
    if not staff:
        wait = await limiter.hit(f"studio:{user.id}", get_settings().studio_rate_limit_per_hour, 3600)
        if wait is not None:
            raise AppError(
                "RATE_LIMITED",
                "Bạn đã yêu cầu sinh quá nhiều lần, vui lòng thử lại sau",
                429,
                {"retry_after": wait},
                headers={"Retry-After": str(wait)},
            )
    artifact = StudyArtifact(
        course_id=data.course_id,
        lesson_id=data.lesson_id,
        kind=kind,
        status=StudioStatus.generating,
        fingerprint=fp,
        created_by=user.id,
    )
    db.add(artifact)
    await db.flush()
    job = await create_and_enqueue(db, queue, STUDIO_JOB, artifact.id, created_by=user.id)
    return StudioRequestOut(artifact_id=artifact.id, status=StudioStatus.generating, job_id=job.id)


async def _artifact_with_access(
    db: AsyncSession, user: User, artifact_id: uuid.UUID
) -> tuple[StudyArtifact, Course]:
    artifact = await db.get(StudyArtifact, artifact_id)
    if artifact is None:
        raise not_found("Tài liệu học")
    course = await ensure_scope(db, user, artifact.course_id, artifact.lesson_id)
    return artifact, course


async def artifact_out(db: AsyncSession, user: User, artifact: StudyArtifact) -> ArtifactOut:
    fp = fingerprint(await load_scope_chunks(db, artifact.course_id, artifact.lesson_id))
    known = (
        await db.scalars(
            select(FlashcardReview.card_no).where(
                FlashcardReview.user_id == user.id,
                FlashcardReview.artifact_id == artifact.id,
                FlashcardReview.known,
            )
        )
    ).all()
    return ArtifactOut(
        id=artifact.id,
        course_id=artifact.course_id,
        lesson_id=artifact.lesson_id,
        kind=artifact.kind,
        status=artifact.status,
        content_md=artifact.content_md,
        cards=artifact.cards,
        citations=artifact.citations,
        error_msg=artifact.error_msg,
        stale=artifact.reviewed_at is None and artifact.fingerprint != fp,
        reviewed=artifact.reviewed_at is not None,
        created_at=artifact.created_at,
        known_cards=sorted(known),
    )


async def get_artifact(db: AsyncSession, user: User, artifact_id: uuid.UUID) -> ArtifactOut:
    artifact, _ = await _artifact_with_access(db, user, artifact_id)
    return await artifact_out(db, user, artifact)


def _card_key(card: dict) -> str:
    return " ".join(str(card.get("front", "")).lower().split())


async def _remap_card_reviews(
    db: AsyncSession, artifact_id: uuid.UUID, old_cards: list[dict], new_cards: list[dict]
) -> None:
    """FlashcardReview gắn với vị trí thẻ (card_no). Giảng viên sửa danh sách thẻ (xóa / chèn / đổi thứ tự) thì
    dời dấu "Nhớ" theo nội dung mặt trước: thẻ cũ khớp mặt trước với thẻ mới (lần lượt, cho cả thẻ trùng) giữ dấu
    ở vị trí mới; thẻ bị xóa hoặc đổi mặt trước thì bỏ dấu. Xóa hết rồi chèn lại để không đụng khóa chính."""
    if old_cards == new_cards:
        return
    free: dict[str, list[int]] = {}
    for i, card in enumerate(new_cards):
        free.setdefault(_card_key(card), []).append(i)
    mapping: dict[int, int] = {}
    for i, card in enumerate(old_cards):
        slots = free.get(_card_key(card))
        if slots:
            mapping[i] = slots.pop(0)
    rows = (
        await db.execute(
            select(
                FlashcardReview.user_id,
                FlashcardReview.card_no,
                FlashcardReview.known,
                FlashcardReview.reviewed_at,
            ).where(FlashcardReview.artifact_id == artifact_id)
        )
    ).all()
    await db.execute(delete(FlashcardReview).where(FlashcardReview.artifact_id == artifact_id))
    kept = [
        {
            "user_id": r.user_id,
            "artifact_id": artifact_id,
            "card_no": mapping[r.card_no],
            "known": r.known,
            "reviewed_at": r.reviewed_at,
        }
        for r in rows
        if r.card_no in mapping
    ]
    if kept:
        await db.execute(insert(FlashcardReview), kept)


async def update_artifact(
    db: AsyncSession, user: User, artifact_id: uuid.UUID, data: ArtifactUpdate
) -> ArtifactOut:
    """Giảng viên sửa: lưu nội dung mới, bỏ nguồn không còn được nhắc tới, đánh dấu đã duyệt."""
    artifact, course = await _artifact_with_access(db, user, artifact_id)
    if not is_course_staff(course, user):
        raise forbidden("Chỉ giảng viên của khóa được sửa")
    if artifact.status != StudioStatus.ready:
        raise AppError("NOT_READY", "Chỉ sửa được bản đã sinh xong", 409)
    if artifact.kind == ArtifactKind.flashcards:
        if data.cards is None:
            raise AppError("VALIDATION_ERROR", "Cần gửi danh sách thẻ", 422)
        new_cards = [c.model_dump() for c in data.cards]
        await _remap_card_reviews(db, artifact.id, artifact.cards or [], new_cards)
        artifact.cards = new_cards
        used = {n for c in data.cards for n in c.sources}
    else:
        if data.content_md is None:
            raise AppError("VALIDATION_ERROR", "Cần gửi nội dung", 422)
        artifact.content_md = data.content_md
        used = cited_numbers(data.content_md)
    artifact.citations = [c for c in artifact.citations if c["n"] in used]
    artifact.reviewed_by = user.id
    artifact.reviewed_at = utcnow()
    await db.commit()
    return await artifact_out(db, user, artifact)


async def review_card(
    db: AsyncSession, user: User, artifact_id: uuid.UUID, card_no: int, known: bool
) -> None:
    artifact, _ = await _artifact_with_access(db, user, artifact_id)
    if (
        artifact.kind != ArtifactKind.flashcards
        or not artifact.cards
        or not 0 <= card_no < len(artifact.cards)
    ):
        raise not_found("Thẻ")
    review = await db.get(FlashcardReview, (user.id, artifact.id, card_no))
    if review is None:
        db.add(FlashcardReview(user_id=user.id, artifact_id=artifact.id, card_no=card_no, known=known))
    else:
        review.known = known
        review.reviewed_at = utcnow()
    await db.commit()


# ---------- gợi ý hỏi tiếp (S5) ----------


class _Followups(BaseModel):
    questions: list[str] = Field(default_factory=list)


async def followups(db: AsyncSession, llm: LLMClient, user: User, message_id: uuid.UUID) -> FollowupsOut:
    """3 câu hỏi gợi ý sau một câu trả lời của chính người dùng. Sinh lần đầu (model rẻ) rồi lưu; lỗi AI thì trả
    danh sách rỗng (không lưu) để giao diện chỉ việc không hiện gợi ý."""
    message = await db.scalar(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.id == message_id,
            ChatSession.user_id == user.id,
            ChatMessage.role == ChatRole.assistant,
        )
    )
    if message is None:
        raise not_found("Tin nhắn")
    if message.followups is not None:
        return FollowupsOut(questions=message.followups)
    if message.refused or not message.content.strip():
        return FollowupsOut(questions=[])
    question = await db.scalar(
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == message.session_id,
            ChatMessage.role == ChatRole.user,
            ChatMessage.created_at <= message.created_at,
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )
    chunk_ids = [uuid.UUID(c["chunk_id"]) for c in message.citations]
    headings = (
        (await db.scalars(select(Chunk.heading_path).where(Chunk.id.in_(chunk_ids)).distinct())).all()
        if chunk_ids
        else []
    )
    prompt = load_prompt("tutor_followups").render(
        question=question or "",
        answer=message.content,
        sections="\n".join(f"- {h}" for h in headings if h) or "-",
    )
    try:
        result, _ = await llm.generate_json(
            prompt, _Followups, op="tutor_followups", model=get_settings().llm_cheap_model
        )
    except Exception:
        logger.warning("Không sinh được gợi ý hỏi tiếp cho tin %s", message_id, exc_info=True)
        return FollowupsOut(questions=[])
    questions = [" ".join(q.split())[:150] for q in result.questions if q.strip()][:3]
    message.followups = questions
    await db.commit()
    return FollowupsOut(questions=questions)
