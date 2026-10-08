import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import LLMClient, get_llm_client
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.pagination import PageParams, page_params
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.core.storage import Storage, get_storage
from app.modules.auth.models import User
from app.modules.jobs.queue import JobQueue, get_queue
from app.modules.studio import notes, service
from app.modules.studio.models import ArtifactKind
from app.modules.studio.schemas import (
    ArtifactOut,
    ArtifactUpdate,
    CardReviewIn,
    ChunkOut,
    DocumentOut,
    FileUrlOut,
    FollowupsOut,
    NoteFromMessageIn,
    NoteIn,
    NoteOut,
    NotePage,
    NotesSynthesizeIn,
    NoteSynthOut,
    NoteUpdate,
    StudioOverview,
    StudioRequestIn,
    StudioRequestOut,
)

router = APIRouter(prefix="/api/v1", tags=["studio"])


# ---------- tài liệu và nguồn ----------


@router.get("/lessons/{lesson_id}/documents", response_model=list[DocumentOut])
async def lesson_documents(
    lesson_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Tài liệu PDF đã xử lý xong của bài + hướng dẫn (tóm tắt, chủ đề, câu hỏi gợi ý). Quyền như xem bài học."""
    return await service.lesson_documents(db, user, lesson_id)


@router.get("/sources/{source_id}/file", response_model=FileUrlOut)
async def source_file(
    source_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    """URL ký sẵn (1 giờ) để mở file PDF; thêm #page=N để nhảy tới trang."""
    return FileUrlOut(url=await service.source_file_url(db, storage, user, source_id))


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
async def chunk_detail(
    chunk_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Toàn văn một đoạn tài liệu (xem trước nguồn [n])."""
    return await service.chunk_detail(db, user, chunk_id)


# ---------- studio ----------


@router.get("/studio", response_model=StudioOverview)
async def studio_overview(
    course_id: uuid.UUID,
    lesson_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trạng thái 5 loại tài liệu học của phạm vi (một bài, hoặc cả khóa khi không có lesson_id)."""
    return await service.overview(db, user, course_id, lesson_id)


@router.post("/studio/{kind}", response_model=StudioRequestOut)
async def request_artifact(
    kind: ArtifactKind,
    data: StudioRequestIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    queue: JobQueue = Depends(get_queue),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    """Có bản còn mới thì 200 kèm artifact_id; không thì tạo bản mới, 202 kèm job_id.
    409 NO_CONTENT (chưa có tài liệu), 403 khi học viên dùng force, 429 RATE_LIMITED (học viên quá 10 lần/giờ)."""
    out = await service.request_artifact(db, queue, limiter, user, kind, data)
    if out.job_id is not None:
        response.status_code = 202
    return out


@router.get("/studio/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(
    artifact_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.get_artifact(db, user, artifact_id)


@router.patch("/studio/artifacts/{artifact_id}", response_model=ArtifactOut)
async def update_artifact(
    artifact_id: uuid.UUID,
    data: ArtifactUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Chủ khóa / admin sửa nội dung; bản đã sửa được đánh dấu đã duyệt, không bị sinh lại tự động."""
    return await service.update_artifact(db, user, artifact_id, data)


@router.put("/studio/artifacts/{artifact_id}/cards/{card_no}", status_code=204)
async def review_card(
    artifact_id: uuid.UUID,
    card_no: int,
    data: CardReviewIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.review_card(db, user, artifact_id, card_no, data.known)


@router.post("/tutor/messages/{message_id}/followups", response_model=FollowupsOut)
async def followups(
    message_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
):
    """3 câu hỏi gợi ý sau một câu trả lời (sinh lần đầu rồi lưu). Lỗi AI thì trả danh sách rỗng."""
    return await service.followups(db, llm, user, message_id)


# ---------- ghi chú ----------


@router.get("/notes", response_model=NotePage)
async def list_notes(
    course_id: uuid.UUID | None = None,
    lesson_id: uuid.UUID | None = None,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await notes.list_notes(db, user, course_id, lesson_id, params)


@router.post("/notes", response_model=NoteOut, status_code=201)
async def create_note(
    data: NoteIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await notes.create_note(db, user, data)


@router.post("/notes/from-message", response_model=NoteOut, status_code=201)
async def note_from_message(
    data: NoteFromMessageIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Lưu câu trả lời AI Tutor (của chính mình) thành ghi chú, giữ trích nguồn."""
    return await notes.note_from_message(db, user, data)


@router.post("/notes/synthesize", response_model=NoteSynthOut, status_code=202)
async def synthesize(
    data: NotesSynthesizeIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    queue: JobQueue = Depends(get_queue),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    """Gộp các ghi chú (cùng khóa) thành một đề cương: tạo ghi chú mới đang tổng hợp, job nền điền nội dung.
    429 RATE_LIMITED khi quá hạn mức mỗi giờ (chung hạn mức Studio)."""
    return await notes.synthesize(db, queue, limiter, user, data)


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: uuid.UUID,
    data: NoteUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await notes.update_note(db, user, note_id, data)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    await notes.delete_note(db, user, note_id)
