"""Trạng thái tài liệu trong phạm vi hỏi của AI Tutor: hỏi được chưa, nếu chưa thì vì sao.

Trước đây chỉ có một câu "Tài liệu đang được xử lý" cho mọi trường hợp 0 chunk, kể cả khi tài liệu đã xử lý
xong bằng model embedding khác (đổi provider) hoặc xử lý lỗi. Ở đây tách rõ từng trường hợp."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval import SearchScope, count_ready_chunks
from app.modules.courses.models import Lesson, Section
from app.modules.materials.models import Chunk, Source, SourceStatus
from app.modules.tutor.schemas import AvailabilityOut

DRAFT_COURSE_SCOPE_MESSAGE = "Hỏi cả khóa chỉ dùng được khi khóa đã xuất bản"
MODEL_MISMATCH_MESSAGE = (
    "Tài liệu đã được xử lý bằng model AI khác với model đang dùng. "
    "Hãy báo giảng viên hoặc quản trị viên xử lý lại tài liệu."
)
FAILED_MESSAGE = "Tài liệu xử lý không thành công. Giảng viên cần tải lại hoặc bấm “Xử lý lại”."
EMPTY_MESSAGE = "Bài này chưa có tài liệu cho AI Tutor."
NO_TEXT_MESSAGE = "Tài liệu của bài này chưa có nội dung chữ để AI Tutor đọc."


def processing_message(n: int) -> str:
    return (
        f"Tài liệu đang được xử lý ({n} tài liệu). "
        "Bạn vẫn có thể đặt câu hỏi: AI sẽ trả lời ngay khi xử lý xong."
    )


@dataclass(frozen=True)
class ScopeState:
    ready_chunks: int  # chunk Tutor tìm được (đúng model, source ready; theo khóa thì khóa đã publish)
    processing_docs: int  # source pending / processing
    failed_docs: int
    ready_docs: int
    other_model_chunks: int  # chunk của source ready nhưng embedding bằng model khác


def _sources_in(scope: SearchScope):
    if scope.lesson_id is not None:
        return Source.lesson_id == scope.lesson_id
    lessons = select(Lesson.id).join(Section, Section.id == Lesson.section_id)
    return Source.lesson_id.in_(lessons.where(Section.course_id == scope.course_id))


async def scope_state(db: AsyncSession, scope: SearchScope, embedding_model: str) -> ScopeState:
    by_status = dict(
        (
            await db.execute(
                select(Source.status, func.count()).where(_sources_in(scope)).group_by(Source.status)
            )
        ).all()
    )
    other = select(func.count(Chunk.id)).join(Source, Source.id == Chunk.source_id)
    other = other.where(
        Chunk.course_id == scope.course_id,
        Chunk.embedding_model != embedding_model,
        Source.status == SourceStatus.ready,
    )
    if scope.lesson_id is not None:
        other = other.where(Chunk.lesson_id == scope.lesson_id)
    return ScopeState(
        ready_chunks=await count_ready_chunks(db, scope, embedding_model),
        processing_docs=by_status.get(SourceStatus.pending, 0) + by_status.get(SourceStatus.processing, 0),
        failed_docs=by_status.get(SourceStatus.failed, 0),
        ready_docs=by_status.get(SourceStatus.ready, 0),
        other_model_chunks=await db.scalar(other) or 0,
    )


def describe(st: ScopeState, *, draft_course_scope: bool) -> AvailabilityOut:
    """Thứ tự ưu tiên khi chưa hỏi được: khóa nháp > đang xử lý > khác model > lỗi > chưa có tài liệu.
    Đang xử lý đứng trước: còn tài liệu sắp xong thì học viên nên chờ (và gửi câu hỏi chờ được)."""
    base = {"ready_chunks": st.ready_chunks, "processing_docs": st.processing_docs}
    if draft_course_scope:
        return AvailabilityOut(
            available=False, message=DRAFT_COURSE_SCOPE_MESSAGE, state="draft", can_queue=False, **base
        )
    if st.ready_chunks > 0:
        return AvailabilityOut(available=True, message=None, state="ready", can_queue=False, **base)
    if st.processing_docs > 0:
        return AvailabilityOut(
            available=False,
            message=processing_message(st.processing_docs),
            state="processing",
            can_queue=True,
            **base,
        )
    if st.other_model_chunks > 0:
        state, message = "model_mismatch", MODEL_MISMATCH_MESSAGE
    elif st.failed_docs > 0:
        state, message = "failed", FAILED_MESSAGE
    else:
        state, message = "empty", NO_TEXT_MESSAGE if st.ready_docs else EMPTY_MESSAGE
    return AvailabilityOut(available=False, message=message, state=state, can_queue=False, **base)
