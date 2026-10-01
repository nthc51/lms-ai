from pydantic import BaseModel, Field, model_validator

from app.modules.quiz.models import Difficulty


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
    count: int = Field(10, ge=1, le=30)
    difficulty: DifficultyMix = Field(default_factory=DifficultyMix)
