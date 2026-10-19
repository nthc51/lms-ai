"""Số liệu cho dashboard giảng viên: số liệu cơ bản (A8) và phân tích lớp học (B7: câu hay sai, bài yếu,
học viên cần để ý)."""

import uuid

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.pagination import PageParams, paginate
from app.core.time import utcnow
from app.modules.analytics.schemas import (
    CourseAnalytics,
    CourseInsights,
    HardQuestion,
    LessonStat,
    QuizStat,
    StudentAtRisk,
    TutorFeedbackItem,
    TutorFeedbackPage,
    TutorStat,
    WeakLesson,
    WrongOption,
)
from app.modules.auth.models import User
from app.modules.courses.models import Course, Lesson, Section
from app.modules.enrollment.models import Enrollment, LessonProgress, ProgressStatus
from app.modules.materials.models import Chunk
from app.modules.quiz.models import AttemptAnswer, AttemptStatus, Question, Quiz, QuizAttempt
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession


async def course_analytics(db: AsyncSession, course: Course) -> CourseAnalytics:
    enrollments, completed = (
        await db.execute(
            select(func.count(), func.count(Enrollment.completed_at)).where(Enrollment.course_id == course.id)
        )
    ).one()

    done = (
        select(LessonProgress.lesson_id, func.count().label("n"))
        .join(
            Enrollment,
            and_(Enrollment.user_id == LessonProgress.user_id, Enrollment.course_id == course.id),
        )
        .where(LessonProgress.status == ProgressStatus.done)
        .group_by(LessonProgress.lesson_id)
        .subquery()
    )
    lesson_rows = (
        await db.execute(
            select(Lesson.id, Lesson.title, Section.title, func.coalesce(done.c.n, 0))
            .join(Section, Section.id == Lesson.section_id)
            .outerjoin(done, done.c.lesson_id == Lesson.id)
            .where(Section.course_id == course.id)
            .order_by(Section.position, Lesson.position, Lesson.id)
        )
    ).all()
    lessons = [
        LessonStat(
            lesson_id=lesson_id,
            title=title,
            section_title=section_title,
            done_count=n,
            completion_rate=round(n / enrollments, 4) if enrollments else 0.0,
        )
        for lesson_id, title, section_title, n in lesson_rows
    ]

    finished = QuizAttempt.status.in_((AttemptStatus.completed, AttemptStatus.timed_out))
    quiz_rows = (
        await db.execute(
            select(
                Quiz.id,
                Quiz.lesson_id,
                Quiz.title,
                Quiz.status,
                func.count(QuizAttempt.id),
                func.count(distinct(QuizAttempt.user_id)),
                func.avg(QuizAttempt.score),
                func.count(QuizAttempt.id).filter(QuizAttempt.score >= Quiz.pass_score),
            )
            .join(Lesson, Lesson.id == Quiz.lesson_id)
            .join(Section, Section.id == Lesson.section_id)
            .outerjoin(QuizAttempt, and_(QuizAttempt.quiz_id == Quiz.id, finished))
            .where(Section.course_id == course.id)
            .group_by(Quiz.id)
            .order_by(Quiz.created_at, Quiz.id)
        )
    ).all()
    quizzes = [
        QuizStat(
            quiz_id=quiz_id,
            lesson_id=lesson_id,
            title=title,
            status=status,
            attempts=n,
            students=students,
            avg_score=round(float(avg), 2) if avg is not None else None,
            pass_rate=round(passed / n, 4) if n else None,
        )
        for quiz_id, lesson_id, title, status, n, students, avg, passed in quiz_rows
    ]

    sessions, questions, refused = (
        await db.execute(
            select(
                func.count(distinct(ChatSession.id)),
                func.count(ChatMessage.id).filter(ChatMessage.role == ChatRole.user),
                func.count(ChatMessage.id).filter(ChatMessage.refused.is_(True)),
            )
            .select_from(ChatSession)
            .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
            .where(ChatSession.course_id == course.id)
        )
    ).one()
    return CourseAnalytics(
        course_id=course.id,
        enrollments=enrollments,
        completed_enrollments=completed,
        lessons=lessons,
        quizzes=quizzes,
        tutor=TutorStat(sessions=sessions, questions=questions, refused_answers=refused),
    )


async def downvoted_answers(
    db: AsyncSession, params: PageParams, course_id: uuid.UUID | None = None, with_student: bool = False
) -> TutorFeedbackPage:
    """Câu trả lời bị bấm 👎, mới nhất trước. course_id=None: mọi khóa (admin)."""
    question_msg = aliased(ChatMessage)
    question = (
        select(question_msg.content)
        .where(
            question_msg.session_id == ChatMessage.session_id,
            question_msg.role == ChatRole.user,
            question_msg.created_at <= ChatMessage.created_at,
        )
        .order_by(question_msg.created_at.desc(), question_msg.id.desc())
        .limit(1)
        .correlate(ChatMessage)
        .scalar_subquery()
    )
    stmt = (
        select(
            ChatMessage,
            question,
            Course.id,
            Course.title,
            Course.slug,
            Lesson.id,
            Lesson.title,
            User.full_name,
        )
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .join(Course, Course.id == ChatSession.course_id)
        .join(User, User.id == ChatSession.user_id)
        .outerjoin(Lesson, Lesson.id == ChatSession.lesson_id)
        .where(ChatMessage.role == ChatRole.assistant, ChatMessage.feedback == -1)
    )
    if course_id is not None:
        stmt = stmt.where(ChatSession.course_id == course_id)
    total, paged = await paginate(db, stmt.order_by(ChatMessage.created_at.desc(), ChatMessage.id), params)
    rows = (await db.execute(paged)).all()
    items = [
        TutorFeedbackItem(
            message_id=m.id,
            question=q,
            answer=m.content,
            refused=m.refused,
            created_at=m.created_at,
            course_id=cid,
            course_title=ctitle,
            course_slug=slug,
            lesson_id=lid,
            lesson_title=ltitle,
            student_name=student if with_student else None,
        )
        for m, q, cid, ctitle, slug, lid, ltitle, student in rows
    ]
    return TutorFeedbackPage(items=items, total=total, page=params.page, size=params.size)


# ---------- B7: phân tích lớp học ----------

MIN_ANSWERS = 3  # ít hơn thì tỉ lệ sai chưa nói lên gì
HARD_LIMIT = 10
WEAK_LIMIT = 5
RISK_LIMIT = 20
LOW_SCORE = 50.0  # điểm quiz trung bình (phần trăm) dưới mức này là thấp
INACTIVE_DAYS = 7


async def course_insights(db: AsyncSession, course: Course) -> CourseInsights:
    """Câu hay sai, bài yếu, học viên cần để ý. Chỉ tính bài quiz đã nộp (completed / timed_out)."""
    finished = QuizAttempt.status.in_((AttemptStatus.completed, AttemptStatus.timed_out))
    course_quiz_attempts = (
        select(QuizAttempt.id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Lesson, Lesson.id == Quiz.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course.id, finished)
    )
    return CourseInsights(
        course_id=course.id,
        min_answers=MIN_ANSWERS,
        hard_questions=await _hard_questions(db, course_quiz_attempts),
        weak_lessons=await _weak_lessons(db, course, finished),
        students_at_risk=await _students_at_risk(db, course, finished),
    )


async def _hard_questions(db: AsyncSession, attempts) -> list[HardQuestion]:
    stats = (
        select(
            AttemptAnswer.question_id,
            func.count().label("answers"),
            func.count().filter(AttemptAnswer.is_correct.is_(False)).label("wrong"),
        )
        .where(AttemptAnswer.attempt_id.in_(attempts))
        .group_by(AttemptAnswer.question_id)
        .subquery()
    )
    rate = stats.c.wrong * 1.0 / stats.c.answers
    rows = (
        await db.execute(
            select(Question, stats.c.answers, stats.c.wrong, Lesson.title, Chunk.page_no)
            .join(stats, stats.c.question_id == Question.id)
            .join(Lesson, Lesson.id == Question.lesson_id)
            .outerjoin(Chunk, Chunk.id == Question.source_chunk_id)
            .where(stats.c.answers >= MIN_ANSWERS, stats.c.wrong > 0)
            .order_by(rate.desc(), stats.c.wrong.desc(), Question.id)
            .limit(HARD_LIMIT)
        )
    ).all()
    if not rows:
        return []
    picks = (
        await db.execute(
            select(AttemptAnswer.question_id, AttemptAnswer.selected_option_id, func.count())
            .where(
                AttemptAnswer.attempt_id.in_(attempts),
                AttemptAnswer.is_correct.is_(False),
                AttemptAnswer.question_id.in_([q.id for q, *_ in rows]),
            )
            .group_by(AttemptAnswer.question_id, AttemptAnswer.selected_option_id)
        )
    ).all()
    top: dict[uuid.UUID, tuple[str, int]] = {}
    for qid, opt, n in sorted(picks, key=lambda p: (-p[2], p[1])):
        top.setdefault(qid, (opt, n))
    out = []
    for q, answers, wrong, lesson_title, page in rows:
        texts = {o["id"]: o["text"] for o in q.options}
        tw = top.get(q.id)
        out.append(
            HardQuestion(
                question_id=q.id,
                stem=q.stem,
                lesson_id=q.lesson_id,
                lesson_title=lesson_title,
                answers=answers,
                wrong=wrong,
                wrong_rate=round(wrong / answers, 4),
                correct_option=q.correct_option_id,
                top_wrong=WrongOption(id=tw[0], text=texts.get(tw[0], ""), count=tw[1]) if tw else None,
                source_page=page,
            )
        )
    return out


async def _weak_lessons(db: AsyncSession, course: Course, finished) -> list[WeakLesson]:
    quiz_stats = (
        select(
            Quiz.lesson_id, func.count(QuizAttempt.id).label("n"), func.avg(QuizAttempt.score).label("avg")
        )
        .join(QuizAttempt, and_(QuizAttempt.quiz_id == Quiz.id, finished))
        .group_by(Quiz.lesson_id)
        .subquery()
    )
    asked = (
        select(ChatSession.lesson_id, func.count(ChatMessage.id).label("n"))
        .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.course_id == course.id, ChatMessage.role == ChatRole.user)
        .group_by(ChatSession.lesson_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(
                Lesson.id,
                Lesson.title,
                Section.title,
                func.coalesce(quiz_stats.c.n, 0),
                quiz_stats.c.avg,
                func.coalesce(asked.c.n, 0),
            )
            .join(Section, Section.id == Lesson.section_id)
            .outerjoin(quiz_stats, quiz_stats.c.lesson_id == Lesson.id)
            .outerjoin(asked, asked.c.lesson_id == Lesson.id)
            .where(Section.course_id == course.id, or_(quiz_stats.c.n > 0, asked.c.n > 0))
            .order_by(quiz_stats.c.avg.asc().nulls_last(), func.coalesce(asked.c.n, 0).desc(), Lesson.id)
            .limit(WEAK_LIMIT)
        )
    ).all()
    return [
        WeakLesson(
            lesson_id=lid,
            title=title,
            section_title=section_title,
            attempts=n,
            avg_score=round(float(avg), 2) if avg is not None else None,
            tutor_questions=q,
        )
        for lid, title, section_title, n, avg, q in rows
    ]


async def _students_at_risk(db: AsyncSession, course: Course, finished) -> list[StudentAtRisk]:
    lesson_ids = (
        select(Lesson.id).join(Section, Section.id == Lesson.section_id).where(Section.course_id == course.id)
    )
    total_lessons = await db.scalar(select(func.count()).select_from(lesson_ids.subquery())) or 0
    students = (
        await db.execute(
            select(User.id, User.full_name, Enrollment.enrolled_at)
            .join(Enrollment, Enrollment.user_id == User.id)
            .where(Enrollment.course_id == course.id, Enrollment.completed_at.is_(None))
        )
    ).all()
    if not students:
        return []
    ids = [s[0] for s in students]
    progress = dict(
        (
            await db.execute(
                select(
                    LessonProgress.user_id,
                    func.count().filter(LessonProgress.status == ProgressStatus.done),
                )
                .where(LessonProgress.user_id.in_(ids), LessonProgress.lesson_id.in_(lesson_ids))
                .group_by(LessonProgress.user_id)
            )
        ).all()
    )
    touched = dict(
        (
            await db.execute(
                select(LessonProgress.user_id, func.max(LessonProgress.updated_at))
                .where(LessonProgress.user_id.in_(ids), LessonProgress.lesson_id.in_(lesson_ids))
                .group_by(LessonProgress.user_id)
            )
        ).all()
    )
    quiz = {
        uid: (avg, last)
        for uid, avg, last in (
            await db.execute(
                select(
                    QuizAttempt.user_id,
                    func.avg(QuizAttempt.score).filter(finished),
                    func.max(QuizAttempt.started_at),
                )
                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
                .where(QuizAttempt.user_id.in_(ids), Quiz.lesson_id.in_(lesson_ids))
                .group_by(QuizAttempt.user_id)
            )
        ).all()
    }
    asked = dict(
        (
            await db.execute(
                select(ChatSession.user_id, func.max(ChatMessage.created_at))
                .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
                .where(
                    ChatSession.course_id == course.id,
                    ChatSession.user_id.in_(ids),
                    ChatMessage.role == ChatRole.user,
                )
                .group_by(ChatSession.user_id)
            )
        ).all()
    )
    now = utcnow()
    out = []
    for uid, name, enrolled_at in students:
        avg, quiz_last = quiz.get(uid, (None, None))
        last = max(t for t in (enrolled_at, touched.get(uid), quiz_last, asked.get(uid)) if t is not None)
        reasons = []
        if avg is not None and avg < LOW_SCORE:
            reasons.append(f"Điểm quiz trung bình {round(float(avg))}%")
        idle = (now - last).days
        if idle >= INACTIVE_DAYS:
            reasons.append(f"Không học {idle} ngày")
        if not reasons:
            continue
        done = progress.get(uid, 0)
        out.append(
            StudentAtRisk(
                user_id=uid,
                full_name=name,
                progress_pct=round(100 * done / total_lessons) if total_lessons else 0,
                avg_score=round(float(avg), 2) if avg is not None else None,
                last_active_at=last,
                reasons=reasons,
            )
        )
    out.sort(key=lambda s: s.last_active_at)
    return out[:RISK_LIMIT]
