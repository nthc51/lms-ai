import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.auth.models import Role, TeacherStatus


def _lower(v: str) -> str:
    return v.strip().lower()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    role: Literal["student", "teacher"] = "student"

    normalize_email = field_validator("email")(
        _lower
    )  # tên không được bắt đầu bằng "_" (pydantic coi là private)


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    normalize_email = field_validator("email")(
        _lower
    )  # tên không được bắt đầu bằng "_" (pydantic coi là private)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResendVerificationIn(BaseModel):
    email: EmailStr

    normalize_email = field_validator("email")(_lower)


class ForgotPasswordIn(BaseModel):
    email: EmailStr

    normalize_email = field_validator("email")(_lower)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = " ".join(v.split())  # bỏ khoảng trắng thừa ở giữa và hai đầu
        if not v:
            raise ValueError("Họ tên không được để trống")
        return v


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    teacher_status: TeacherStatus | None
    review_note: str | None = None  # lý do bị từ chối duyệt giảng viên (nếu có)
    email_verified: bool = False  # đọc từ property User.email_verified
