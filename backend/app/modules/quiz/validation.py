"""Luật của một câu hỏi trắc nghiệm hợp lệ (spec 5.4 bước 4). Dùng cho output của AI và khi giảng viên sửa câu."""

import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.modules.quiz.models import Difficulty

OPTION_IDS = ("A", "B", "C", "D")


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


class OptionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=300)


class QuestionContent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    stem: str = Field(min_length=10, max_length=1000)
    options: list[OptionIn]
    correct_option_id: str = Field(min_length=1, max_length=8)
    explanation: str = Field(default="", max_length=2000)
    difficulty: Difficulty

    @model_validator(mode="after")
    def _one_correct_of_four_distinct(self) -> "QuestionContent":
        if len(self.options) != 4:
            raise ValueError("Câu hỏi phải có đúng 4 lựa chọn")
        ids = [o.id for o in self.options]
        if len(set(ids)) != 4:
            raise ValueError("Mã lựa chọn bị trùng")
        if len({_norm(o.text) for o in self.options}) != 4:
            raise ValueError("Có lựa chọn trùng nhau")
        # mã lựa chọn không trùng + correct_option_id nằm trong đó ⇔ đúng một đáp án đúng
        if self.correct_option_id not in ids:
            raise ValueError("Đáp án đúng phải là một trong 4 lựa chọn")
        return self

    def normalized(self) -> "QuestionContent":
        """Đổi mã lựa chọn về A–D theo thứ tự, giữ nguyên đáp án đúng."""
        mapping = {o.id: OPTION_IDS[i] for i, o in enumerate(self.options)}
        return self.model_copy(
            update={
                "options": [OptionIn(id=OPTION_IDS[i], text=o.text) for i, o in enumerate(self.options)],
                "correct_option_id": mapping[self.correct_option_id],
            }
        )


class DraftOption(BaseModel):
    id: str
    # Giới hạn chỉ nằm trong JSON schema gửi LLM (không ép lúc parse) để câu sai luật chỉ bị bỏ riêng câu đó.
    text: str = Field(json_schema_extra={"maxLength": 300})


class DraftQuestion(BaseModel):
    """Hình dạng output của AI (schema gửi cho LLM). Lỏng hơn QuestionContent để parse được cả câu sai luật,
    rồi mới kiểm tra từng câu: câu sai chỉ bỏ câu đó, không bỏ cả lô. Schema vẫn dẫn dắt model: enum độ khó,
    đúng 4 lựa chọn, giới hạn độ dài."""

    stem: str = Field(json_schema_extra={"maxLength": 1000})
    options: list[DraftOption] = Field(json_schema_extra={"minItems": 4, "maxItems": 4})
    correct_option_id: str
    explanation: str = Field(json_schema_extra={"maxLength": 2000})
    difficulty: Difficulty

    @model_validator(mode="before")
    @classmethod
    def _fill_missing(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = {"explanation": "", "difficulty": "medium", **data}
        return data

    @field_validator("difficulty", mode="before")
    @classmethod
    def _tolerant_difficulty(cls, v: Any) -> Any:
        # Không bao giờ làm hỏng cả lô vì độ khó lạ: giá trị không hợp lệ (chuỗi lạ, None, số) -> medium.
        v = v.strip().lower() if isinstance(v, str) else v
        return v if v in {d.value for d in Difficulty} else Difficulty.medium.value


class DraftBatch(BaseModel):
    questions: list[DraftQuestion]


class SelfCheckOut(BaseModel):
    answer_option_id: str


def _describe(err: Any) -> str:
    loc = ".".join(str(x) for x in err["loc"])
    return f"{loc}: {err['msg']}" if loc else err["msg"]


def validate_draft(draft: DraftQuestion) -> tuple[QuestionContent | None, str | None]:
    """(câu đã chuẩn hóa, None) nếu hợp lệ; (None, lý do) nếu sai luật — lý do được gửi lại cho LLM khi sinh lại."""
    try:
        return QuestionContent.model_validate(draft.model_dump()).normalized(), None
    except ValidationError as e:
        return None, "; ".join(_describe(err) for err in e.errors())[:300]
