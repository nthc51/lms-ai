import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.pagination import Page
from app.modules.quiz.models import QuizStatus


class LessonStat(BaseModel):
    lesson_id: uuid.UUID
    title: str
    section_title: str
    done_count: int  # số học viên (đang đăng ký) đã hoàn thành bài
    completion_rate: float  # done_count / số đăng ký, 0..1


class QuizStat(BaseModel):
    quiz_id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    status: QuizStatus
    attempts: int  # số bài đã nộp (completed + timed_out)
    students: int
    avg_score: float | None
    pass_rate: float | None  # 0..1


class TutorStat(BaseModel):
    sessions: int
    questions: int
    refused_answers: int


class CourseAnalytics(BaseModel):
    course_id: uuid.UUID
    enrollments: int
    completed_enrollments: int
    lessons: list[LessonStat]
    quizzes: list[QuizStat]
    tutor: TutorStat


class TutorFeedbackItem(BaseModel):
    """Một câu trả lời AI Tutor bị học viên bấm 👎 (D1), kèm câu hỏi ngay trước nó."""

    message_id: uuid.UUID
    question: str | None
    answer: str
    refused: bool
    created_at: datetime
    course_id: uuid.UUID
    course_title: str
    course_slug: str
    lesson_id: uuid.UUID | None
    lesson_title: str | None
    student_name: str | None  # chỉ trả cho admin; giảng viên không thấy ai chê (để học viên dám bấm)


class TutorFeedbackPage(Page[TutorFeedbackItem]):
    pass
