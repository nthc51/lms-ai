import uuid

from pydantic import BaseModel

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
