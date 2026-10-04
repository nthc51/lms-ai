"""Số liệu cơ bản cho dashboard giảng viên (A8). Phân tích sâu (câu hay sai, chủ đề yếu) là B7."""

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.schemas import CourseAnalytics, LessonStat, QuizStat, TutorStat
from app.modules.courses.models import Course, Lesson, Section
from app.modules.enrollment.models import Enrollment, LessonProgress, ProgressStatus
from app.modules.quiz.models import AttemptStatus, Quiz, QuizAttempt
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
