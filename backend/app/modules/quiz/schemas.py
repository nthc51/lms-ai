import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.core.pagination import Page
from app.modules.quiz.models import AttemptStatus, Difficulty, QuestionOrigin, QuizStatus, ReviewStatus
from app.modules.quiz.validation import OptionIn


class DifficultyMix(BaseModel):
    """Tỉ lệ độ khó mong muốn (spec 5.4 bước 1); không cần cộng đúng 1, chỉ cần có ít nhất một giá trị > 0."""

    easy: float = Field(0.3, ge=0, le=1)
    medium: float = Field(0.5, ge=0, le=1)
    hard: float = Field(0.2, ge=0, le=1)

    @model_validator(mode="after")
    def _not_all_zero(self) -> "DifficultyMix":
        if self.easy + self.medium + self.hard <= 0:
            raise ValueError("Tỉ lệ độ khó phải có ít nhất một giá trị lớn hơn 0")
        return self

    def as_mapping(self) -> dict[Difficulty, float]:
        return {Difficulty.easy: self.easy, Difficulty.medium: self.medium, Difficulty.hard: self.hard}


class QuizGenerateIn(BaseModel):
    """Body của POST sinh câu hỏi và cũng là jobs.payload của quiz_gen. Không nhận trường lạ; count phải là số
    nguyên thật (không nhận true hay "7")."""

    model_config = ConfigDict(extra="forbid")

    count: StrictInt = Field(10, ge=1, le=30)
    difficulty: DifficultyMix = Field(default_factory=DifficultyMix)


class OptionOut(BaseModel):
    id: str
    text: str


class QuestionOut(BaseModel):
    """Câu hỏi kèm đáp án — chỉ trả cho giảng viên sở hữu / admin."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lesson_id: uuid.UUID
    stem: str
    options: list[OptionOut]
    correct_option_id: str
    explanation: str
    difficulty: Difficulty
    origin: QuestionOrigin
    review_status: ReviewStatus
    self_check_flag: bool
    ai_original: dict | None
    prompt_version: str | None
    source_chunk_id: uuid.UUID | None
    source_page_no: int | None = None  # trang của đoạn nguồn (màn duyệt hiển thị bên cạnh câu hỏi)
    source_excerpt: str | None = None
    created_at: datetime


class QuestionPage(Page[QuestionOut]):
    pass


class QuestionReview(BaseModel):
    """approve: duyệt; reject: loại; edit: sửa các trường gửi kèm (validate lại đủ luật, đặt edited)."""

    action: Literal["approve", "edit", "reject"]
    stem: str | None = None
    options: list[OptionIn] | None = None
    correct_option_id: str | None = None
    explanation: str | None = None
    difficulty: Difficulty | None = None


class QuizCreate(BaseModel):
    lesson_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    max_attempts: int = Field(1, ge=1, le=20)
    pass_score: float = Field(50, ge=0, le=100)  # phần trăm
    question_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class QuizUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    max_attempts: int | None = Field(None, ge=1, le=20)
    pass_score: float | None = Field(None, ge=0, le=100)
    question_ids: list[uuid.UUID] | None = Field(None, max_length=100)  # chỉ đổi được khi quiz còn nháp


class QuizOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    max_attempts: int
    pass_score: float
    status: QuizStatus
    question_count: int
    created_at: datetime
    attempts_used: int | None = None  # chỉ trả cho học viên: số lần đã làm
    questions: list[QuestionOut] | None = None  # chỉ giảng viên sở hữu / admin (có đáp án)


class QuizPage(Page[QuizOut]):
    pass


class AttemptQuestion(BaseModel):
    """Câu hỏi khi đang làm bài: KHÔNG có đáp án đúng, không có giải thích."""

    id: uuid.UUID
    stem: str
    options: list[OptionOut]


class AttemptOut(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    attempt_no: int
    status: AttemptStatus
    started_at: datetime
    deadline_at: datetime | None  # B1 (tuần 3): luôn None ở A7
    questions: list[AttemptQuestion]
    answers: dict[str, str]  # question_id → selected_option_id đã autosave


class AnswerIn(BaseModel):
    selected_option_id: str = Field(min_length=1, max_length=8)


class AnswerOut(BaseModel):
    question_id: uuid.UUID
    selected_option_id: str
    answered_at: datetime


class FinalAnswer(BaseModel):
    question_id: uuid.UUID
    selected_option_id: str = Field(min_length=1, max_length=8)


class SubmitIn(BaseModel):
    final_answers: list[FinalAnswer] | None = Field(None, max_length=200)  # payload thắng bản autosave


class ResultQuestion(BaseModel):
    """Sau khi nộp: kèm đáp án đúng và giải thích có sẵn của câu hỏi."""

    id: uuid.UUID
    stem: str
    options: list[OptionOut]
    selected_option_id: str | None
    correct_option_id: str
    is_correct: bool
    explanation: str


class AttemptResult(BaseModel):
    attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    attempt_no: int
    status: AttemptStatus
    score: float  # phần trăm, làm tròn 2 chữ số
    passed: bool
    correct_count: int
    total: int
    submitted_at: datetime | None
    questions: list[ResultQuestion]
