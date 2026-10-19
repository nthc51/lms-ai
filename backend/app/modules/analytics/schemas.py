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


class WrongOption(BaseModel):
    id: str  # A–D
    text: str
    count: int  # số lượt chọn phương án sai này


class HardQuestion(BaseModel):
    """Câu hỏi quiz học viên hay làm sai (B7)."""

    question_id: uuid.UUID
    stem: str
    lesson_id: uuid.UUID
    lesson_title: str
    answers: int  # số lượt trả lời trong các bài đã nộp
    wrong: int
    wrong_rate: float  # 0..1
    correct_option: str
    top_wrong: WrongOption | None  # phương án sai được chọn nhiều nhất
    source_page: int | None  # trang tài liệu mà câu hỏi dựa vào


class WeakLesson(BaseModel):
    """Bài học có điểm quiz thấp hoặc học viên hỏi AI Tutor nhiều (B7)."""

    lesson_id: uuid.UUID
    title: str
    section_title: str
    attempts: int  # số bài quiz đã nộp ở các quiz của bài
    avg_score: float | None
    tutor_questions: int  # số câu học viên hỏi AI Tutor trong phiên gắn với bài


class StudentAtRisk(BaseModel):
    """Học viên cần giảng viên để ý (B7): điểm quiz trung bình thấp hoặc lâu không học."""

    user_id: uuid.UUID
    full_name: str
    progress_pct: int
    avg_score: float | None
    last_active_at: datetime
    reasons: list[str]


class CourseInsights(BaseModel):
    course_id: uuid.UUID
    min_answers: int  # câu hỏi cần ít nhất chừng này lượt trả lời mới được xếp hạng
    hard_questions: list[HardQuestion]
    weak_lessons: list[WeakLesson]
    students_at_risk: list[StudentAtRisk]
