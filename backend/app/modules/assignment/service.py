"""Bài tập (B5): giảng viên tạo / sửa / xuất bản bài tập, học viên nộp bài, giảng viên xem bài nộp và xác nhận điểm.

Điểm AI gợi ý (submissions.ai_result) do job grade_submission ghi (grading.py) và không bao giờ bị ghi đè khi giảng
viên chấm: điểm cuối nằm ở final_scores / final_total. Học viên chỉ thấy điểm sau khi giảng viên xác nhận."""

import uuid

from sqlalchemy import case, func, null, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.core.storage import Storage
from app.core.time import utcnow
from app.modules.assignment.models import Assignment, AssignmentStatus, Submission, SubmissionStatus
from app.modules.assignment.schemas import (
    AIResult,
    AssignmentCreate,
    AssignmentOut,
    AssignmentPage,
    AssignmentUpdate,
    FileRef,
    GradeIn,
    MySubmission,
    RubricItem,
    RubricItemIn,
    SubmissionDetail,
    SubmissionIn,
    SubmissionListItem,
    SubmissionPage,
)
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, CourseStatus
from app.modules.courses.service import ensure_owner, get_lesson_with_course, get_owned_lesson
from app.modules.enrollment.models import Enrollment
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.inbox import service as inbox
from app.modules.inbox.hub import NotificationHub
from app.modules.inbox.models import NotificationKind
from app.modules.jobs.queue import JobQueue
from app.modules.jobs.service import create_and_enqueue
from app.modules.materials.assets import require_verified_asset
from app.modules.materials.models import Asset, AssetKind

GRADE_JOB = "grade_submission"
TO_REVIEW = (SubmissionStatus.ai_graded, SubmissionStatus.ai_failed)


def _rubric(items: list[RubricItemIn]) -> list[dict]:
    return [
        {
            "key": f"c{i}",
            "criterion": it.criterion,
            "max_points": it.max_points,
            "description": it.description.strip(),
        }
        for i, it in enumerate(items, start=1)
    ]


def _is_staff(course: Course, user: User) -> bool:
    return user.role == Role.admin or course.teacher_id == user.id


def teacher_link(course: Course, assignment: Assignment, submission_id: uuid.UUID | None = None) -> str:
    base = f"/teach/{course.slug}/lessons/{assignment.lesson_id}/assignments/{assignment.id}"
    return f"{base}?bai={submission_id}" if submission_id else base


def student_link(assignment: Assignment) -> str:
    return f"/assignments/{assignment.id}"


async def _context(db: AsyncSession, assignment_id: uuid.UUID) -> tuple[Assignment, Course]:
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None:
        raise not_found("Bài tập")
    _, course = await get_lesson_with_course(db, assignment.lesson_id)
    return assignment, course


async def get_owned_assignment(
    db: AsyncSession, assignment_id: uuid.UUID, user: User
) -> tuple[Assignment, Course]:
    assignment, course = await _context(db, assignment_id)
    ensure_owner(course, user)
    return assignment, course


async def _file_ref(db: AsyncSession, asset_id: uuid.UUID | None) -> FileRef | None:
    if asset_id is None:
        return None
    name = await db.scalar(select(Asset.original_name).where(Asset.id == asset_id))
    return FileRef(asset_id=asset_id, name=name)


async def _my_submission(db: AsyncSession, sub: Submission | None) -> MySubmission | None:
    if sub is None:
        return None
    graded = sub.status == SubmissionStatus.graded
    return MySubmission(
        id=sub.id,
        version=sub.version,
        status=sub.status,
        submitted_at=sub.submitted_at,
        text_content=sub.text_content,
        file=await _file_ref(db, sub.asset_id),
        final_scores=sub.final_scores if graded else None,
        final_total=sub.final_total if graded else None,
        teacher_feedback=sub.teacher_feedback if graded else None,
        graded_at=sub.graded_at if graded else None,
    )


async def _to_out(db: AsyncSession, a: Assignment, user: User, staff: bool) -> AssignmentOut:
    lesson, course = await get_lesson_with_course(db, a.lesson_id)
    out = AssignmentOut(
        id=a.id,
        lesson_id=a.lesson_id,
        lesson_title=lesson.title,
        course_slug=course.slug,
        title=a.title,
        instructions=a.instructions,
        due_at=a.due_at,
        rubric=[RubricItem(**r) for r in a.rubric],
        max_total=sum(r["max_points"] for r in a.rubric),
        status=a.status,
        created_at=a.created_at,
    )
    if staff:
        row = (
            await db.execute(
                select(func.count(), func.count(case((Submission.status.in_(TO_REVIEW), 1)))).where(
                    Submission.assignment_id == a.id
                )
            )
        ).one()
        out.submission_count, out.to_review = row[0], row[1]
    else:
        sub = await db.scalar(
            select(Submission).where(Submission.assignment_id == a.id, Submission.user_id == user.id)
        )
        out.my_submission = await _my_submission(db, sub)
    return out


# ---------- giảng viên: soạn bài tập ----------


async def create_assignment(db: AsyncSession, user: User, data: AssignmentCreate) -> AssignmentOut:
    lesson, _ = await get_owned_lesson(db, data.lesson_id, user)
    assignment = Assignment(
        lesson_id=lesson.id,
        title=data.title,
        instructions=data.instructions,
        due_at=data.due_at,
        rubric=_rubric(data.rubric),
        status=AssignmentStatus.draft,
        created_by=user.id,
    )
    db.add(assignment)
    await db.commit()
    return await _to_out(db, assignment, user, True)


async def _has_submissions(db: AsyncSession, assignment_id: uuid.UUID) -> bool:
    count = await db.scalar(
        select(func.count()).select_from(Submission).where(Submission.assignment_id == assignment_id)
    )
    return count > 0


async def update_assignment(
    db: AsyncSession, user: User, assignment: Assignment, data: AssignmentUpdate
) -> AssignmentOut:
    # khóa dòng: không để một bài nộp chen vào giữa lúc kiểm tra "chưa có bài nộp" và lúc đổi rubric
    await db.refresh(assignment, with_for_update=True)
    if data.rubric is not None:
        if await _has_submissions(db, assignment.id):
            raise AppError("INVALID_STATE", "Đã có bài nộp, không đổi được rubric", 409)
        assignment.rubric = _rubric(data.rubric)
    if data.title is not None:
        assignment.title = data.title
    if data.instructions is not None:
        assignment.instructions = data.instructions
    if "due_at" in data.model_fields_set:
        assignment.due_at = data.due_at
    await db.commit()
    return await _to_out(db, assignment, user, True)


async def delete_assignment(db: AsyncSession, assignment: Assignment) -> None:
    await db.refresh(assignment, with_for_update=True)
    if await _has_submissions(db, assignment.id):
        raise AppError("INVALID_STATE", "Đã có học viên nộp bài, không xóa được bài tập", 409)
    await db.delete(assignment)
    await db.commit()


async def publish_assignment(
    db: AsyncSession, user: User, assignment: Assignment, course: Course, hub: NotificationHub | None = None
) -> AssignmentOut:
    """Xuất bản (idempotent). Khóa đã xuất bản thì báo cho mọi học viên đã đăng ký."""
    await db.refresh(assignment, with_for_update=True)
    notified: list[str] = []
    if assignment.status != AssignmentStatus.published:
        assignment.status = AssignmentStatus.published
        if course.status == CourseStatus.published:
            students = list(
                await db.scalars(select(Enrollment.user_id).where(Enrollment.course_id == course.id))
            )
            notified = inbox.add(
                db,
                students,
                NotificationKind.assignment_published,
                f"Bài tập mới: {assignment.title}",
                student_link(assignment),
                f"Hạn nộp {assignment.due_at:%d/%m/%Y %H:%M} (UTC)" if assignment.due_at else "",
            )
    await db.commit()
    if hub is not None:
        await inbox.publish(hub, notified)
    return await _to_out(db, assignment, user, True)


# ---------- xem bài tập ----------


async def list_lesson_assignments(
    db: AsyncSession, user: User, lesson_id: uuid.UUID, params: PageParams
) -> AssignmentPage:
    """Giảng viên của khóa / admin thấy mọi bài tập (kèm số bài nộp); học viên chỉ thấy bài đã xuất bản (kèm bài
    nộp của mình)."""
    _, course = await ensure_lesson_access(db, lesson_id, user)
    staff = _is_staff(course, user)
    stmt = select(Assignment).where(Assignment.lesson_id == lesson_id)
    if not staff:
        stmt = stmt.where(Assignment.status == AssignmentStatus.published)
    total, paged = await paginate(db, stmt.order_by(Assignment.created_at, Assignment.id), params)
    items = [await _to_out(db, a, user, staff) for a in (await db.scalars(paged)).all()]
    return AssignmentPage(items=items, total=total, page=params.page, size=params.size)


async def get_assignment_for_viewer(db: AsyncSession, user: User, assignment_id: uuid.UUID) -> AssignmentOut:
    assignment, course = await _context(db, assignment_id)
    await ensure_lesson_access(db, assignment.lesson_id, user)
    staff = _is_staff(course, user)
    if not staff and assignment.status != AssignmentStatus.published:
        raise not_found("Bài tập")
    return await _to_out(db, assignment, user, staff)


# ---------- học viên: nộp bài ----------


async def submit(
    db: AsyncSession, queue: JobQueue, user: User, assignment_id: uuid.UUID, data: SubmissionIn
) -> MySubmission:
    """Nộp lần đầu hoặc nộp lại (cập nhật tại chỗ, version + 1) rồi đẩy job AI chấm cho đúng version đó.

    Nộp lại được khi bài chưa được giảng viên xác nhận và chưa quá hạn. Job của version cũ nếu còn chạy thì khi
    xong sẽ không ghi được kết quả (grading.py chỉ ghi khi version còn khớp)."""
    assignment, course = await _context(db, assignment_id)
    await ensure_lesson_access(db, assignment.lesson_id, user)
    if assignment.status != AssignmentStatus.published or _is_staff(course, user):
        raise not_found("Bài tập")
    if assignment.due_at is not None and utcnow() >= assignment.due_at:
        raise AppError("DEADLINE_PASSED", "Đã quá hạn nộp bài", 409)
    if data.asset_id is not None:
        await require_verified_asset(db, data.asset_id, user, AssetKind.submission)
    sub = await db.scalar(
        select(Submission)
        .where(Submission.assignment_id == assignment.id, Submission.user_id == user.id)
        .with_for_update()
    )
    now = utcnow()
    if sub is None:
        sub = Submission(
            assignment_id=assignment.id,
            user_id=user.id,
            text_content=data.text_content,
            asset_id=data.asset_id,
            version=1,
            submitted_at=now,
            status=SubmissionStatus.submitted,
        )
        db.add(sub)
    else:
        if sub.status == SubmissionStatus.graded:
            raise AppError("ALREADY_GRADED", "Bài đã được giảng viên chấm, không nộp lại được", 409)
        sub.text_content = data.text_content
        sub.asset_id = data.asset_id
        sub.version += 1
        sub.submitted_at = now
        sub.status = SubmissionStatus.submitted
        sub.ai_result = None
        sub.ai_error = None
    await db.flush()
    await create_and_enqueue(db, queue, GRADE_JOB, sub.id, sub.version, created_by=user.id)
    return await _my_submission(db, sub)


# ---------- giảng viên: bài nộp và chấm ----------


def _ai_total(sub: Submission) -> float | None:
    return sub.ai_result.get("total") if sub.ai_result else None


def _flagged(sub: Submission) -> int:
    if not sub.ai_result:
        return 0
    return sum(1 for s in sub.ai_result.get("scores", {}).values() if not s.get("evidence_found", True))


async def list_submissions(
    db: AsyncSession,
    assignment: Assignment,
    status: SubmissionStatus | None,
    params: PageParams,
) -> SubmissionPage:
    stmt = (
        select(Submission, User.full_name)
        .join(User, User.id == Submission.user_id)
        .where(Submission.assignment_id == assignment.id)
    )
    if status is not None:
        stmt = stmt.where(Submission.status == status)
    # bài cần giảng viên xử lý lên trước, rồi bài nộp sớm trước
    order = case(
        (Submission.status.in_(TO_REVIEW), 0), (Submission.status == SubmissionStatus.submitted, 1), else_=2
    )
    total, paged = await paginate(db, stmt.order_by(order, Submission.submitted_at, Submission.id), params)
    items = [
        SubmissionListItem(
            id=s.id,
            user_id=s.user_id,
            student_name=name,
            status=s.status,
            version=s.version,
            submitted_at=s.submitted_at,
            ai_total=_ai_total(s),
            final_total=s.final_total,
            flagged=_flagged(s),
        )
        for s, name in (await db.execute(paged)).all()
    ]
    return SubmissionPage(items=items, total=total, page=params.page, size=params.size)


async def get_owned_submission(
    db: AsyncSession, submission_id: uuid.UUID, user: User
) -> tuple[Submission, Assignment, Course]:
    sub = await db.get(Submission, submission_id)
    if sub is None:
        raise not_found("Bài nộp")
    assignment, course = await _context(db, sub.assignment_id)
    try:
        ensure_owner(course, user)
    except AppError:
        raise not_found("Bài nộp") from None
    return sub, assignment, course


async def submission_detail(db: AsyncSession, storage: Storage, sub: Submission) -> SubmissionDetail:
    name = await db.scalar(select(User.full_name).where(User.id == sub.user_id))
    file = await _file_ref(db, sub.asset_id)
    url = None
    if sub.asset_id is not None:
        asset = await db.get(Asset, sub.asset_id)
        if asset is not None:
            url = await storage.presign_get(asset.storage_key, asset.mime, download_name=asset.original_name)
    return SubmissionDetail(
        id=sub.id,
        assignment_id=sub.assignment_id,
        user_id=sub.user_id,
        student_name=name or "",
        status=sub.status,
        version=sub.version,
        submitted_at=sub.submitted_at,
        text_content=sub.text_content,
        file=file,
        file_url=url,
        ai_result=AIResult.model_validate(sub.ai_result) if sub.ai_result else None,
        ai_error=sub.ai_error,
        final_scores=sub.final_scores,
        final_total=sub.final_total,
        teacher_feedback=sub.teacher_feedback,
        graded_at=sub.graded_at,
    )


async def grade(
    db: AsyncSession,
    user: User,
    sub: Submission,
    assignment: Assignment,
    data: GradeIn,
    hub: NotificationHub | None = None,
) -> None:
    """Giảng viên xác nhận điểm (chấm lần đầu hoặc sửa điểm đã chấm). Không đụng tới ai_result."""
    keys = {r["key"]: r for r in assignment.rubric}
    if set(data.scores) != set(keys):
        raise AppError("INVALID_SCORES", "Cần chấm đủ và đúng các tiêu chí của rubric", 422)
    for key, value in data.scores.items():
        top = keys[key]["max_points"]
        if not 0 <= value <= top:
            raise AppError(
                "INVALID_SCORES", f'Điểm tiêu chí "{keys[key]["criterion"]}" phải từ 0 đến {top}', 422
            )
    scores = {k: round(v, 2) for k, v in data.scores.items()}
    sub.final_scores = scores
    sub.final_total = round(sum(scores.values()), 2)
    sub.teacher_feedback = (data.feedback or "").strip() or None
    sub.status = SubmissionStatus.graded
    sub.graded_by = user.id
    sub.graded_at = utcnow()
    notified = inbox.add(
        db,
        [sub.user_id],
        NotificationKind.grade_released,
        f"Đã có điểm bài tập: {assignment.title}",
        student_link(assignment),
        f"{sub.final_total:g}/{sum(r['max_points'] for r in assignment.rubric)} điểm",
    )
    await db.commit()
    if hub is not None:
        await inbox.publish(hub, notified)


async def regrade(db: AsyncSession, queue: JobQueue, user: User, sub: Submission) -> uuid.UUID:
    """Cho AI chấm lại bài chưa được giảng viên xác nhận (vd. AI lỗi lần trước). Trả id job."""
    updated = await db.scalar(
        update(Submission)
        .where(Submission.id == sub.id, Submission.status != SubmissionStatus.graded)
        .values(status=SubmissionStatus.submitted, ai_result=null(), ai_error=None)
        .returning(Submission.version)
    )
    if updated is None:
        raise AppError("ALREADY_GRADED", "Bài đã được chấm; sửa điểm trực tiếp thay vì cho AI chấm lại", 409)
    job = await create_and_enqueue(db, queue, GRADE_JOB, sub.id, updated, created_by=user.id)
    return job.id
