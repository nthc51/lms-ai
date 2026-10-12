"""Tạo dữ liệu cho load test: 1 giảng viên, 20 khóa đã publish (3 chương × 5 bài), 10 học viên đã đăng ký khóa đầu.

Chạy từ backend/ (DB dev của docker compose):  uv run python -m scripts.perf_seed
Ghi thông tin đăng nhập và id bài học vào ../perf/seed.json cho k6.

Email dùng đuôi example.com (trang đăng nhập dùng EmailStr, từ chối .local) và được đánh dấu đã xác nhận
(chưa xác nhận thì đăng nhập nhận 403 EMAIL_NOT_VERIFIED).
"""

import asyncio
import json
import uuid
from pathlib import Path

import app.models_registry  # noqa: F401 — nạp mọi model (FK lessons → assets cần bảng assets)
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.time import utcnow
from app.modules.auth.models import Role, TeacherStatus, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.enrollment.models import Enrollment

PASSWORD = "perf-password-123"
OUT = Path(__file__).resolve().parents[2] / "perf" / "seed.json"


async def main() -> None:
    tag = uuid.uuid4().hex[:6]
    pw = hash_password(PASSWORD)
    now = utcnow()
    async with SessionLocal() as db:
        teacher = User(
            email=f"perf-gv-{tag}@example.com",
            password_hash=pw,
            full_name="GV Perf",
            role=Role.teacher,
            teacher_status=TeacherStatus.approved,
            email_verified_at=now,
        )
        db.add(teacher)
        await db.flush()
        first_course, lesson_ids = None, []
        for c in range(20):
            course = Course(
                teacher_id=teacher.id,
                title=f"Khóa đo tải {c + 1}",
                slug=f"perf-{tag}-{c + 1}",
                description="Dữ liệu load test " * 10,
                status=CourseStatus.published,
            )
            db.add(course)
            await db.flush()
            first_course = first_course or course
            for s in range(3):
                section = Section(course_id=course.id, title=f"Chương {s + 1}", position=s + 1)
                db.add(section)
                await db.flush()
                for i in range(5):
                    lesson = Lesson(
                        section_id=section.id,
                        title=f"Bài {i + 1}",
                        position=i + 1,
                        content_md="# Nội dung\n\n" + "Văn bản bài học. " * 200,
                    )
                    db.add(lesson)
                    await db.flush()
                    if course is first_course:
                        lesson_ids.append(str(lesson.id))
        students = []
        for n in range(10):
            email = f"perf-sv-{tag}-{n}@example.com"
            student = User(
                email=email,
                password_hash=pw,
                full_name=f"SV Perf {n}",
                role=Role.student,
                email_verified_at=now,
            )
            db.add(student)
            await db.flush()
            db.add(Enrollment(user_id=student.id, course_id=first_course.id))
            students.append(email)
        await db.commit()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"password": PASSWORD, "students": students, "lesson_ids": lesson_ids},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Đã tạo 20 khóa, 10 học viên. Ghi {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
