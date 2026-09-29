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

    normalize_email = field_validator("email")(_lower)  # tên không được bắt đầu bằng "_" (pydantic coi là private)


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    normalize_email = field_validator("email")(_lower)  # tên không được bắt đầu bằng "_" (pydantic coi là private)


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
