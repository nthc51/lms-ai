from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.core.time import utcnow
from app.modules.auth.models import EmailToken, RefreshToken, Role, TeacherStatus, User
from app.modules.auth.schemas import LoginIn, RegisterIn
from app.modules.notify import templates
from app.modules.notify.outbox import queue_email

VERIFY = "verify_email"


def _email_taken() -> AppError:
    return AppError("EMAIL_TAKEN", "Email đã được sử dụng", 409)


async def register(db: AsyncSession, data: RegisterIn) -> User:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise _email_taken()
    role = Role(data.role)
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=role,
        teacher_status=TeacherStatus.pending if role == Role.teacher else None,
    )
    db.add(user)
    try:
        await db.flush()  # cần user.id cho link xác nhận
        await _issue_verify_token(db, user)
        if role == Role.teacher and not get_settings().email_verification_required:
            # Không bắt buộc xác nhận email: giảng viên vào hàng chờ ngay, báo admin luôn lúc đăng ký.
            await notify_admins_pending_teacher(db, user)
        await db.commit()
    except IntegrityError:
        # Hai request đăng ký cùng email chạy song song: cả hai qua được bước kiểm tra ở trên,
        # request thua vấp unique constraint (ở flush) → vẫn trả 409 thay vì 500.
        await db.rollback()
        if await db.scalar(select(User.id).where(User.email == email)):
            raise _email_taken() from None
        raise
    return user


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    """Trả về (access_token, refresh_token_raw). Commit luôn cả các thay đổi đang chờ trong session."""
    raw, hashed = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashed,
            expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days),
        )
    )
    await db.commit()
    return create_access_token(user.id, user.role.value), raw


async def login(db: AsyncSession, data: LoginIn) -> tuple[str, str]:
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng", 401)
    if user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    # Kiểm sau mật khẩu: người không biết mật khẩu không dò được email nào chưa xác nhận.
    if get_settings().email_verification_required and user.email_verified_at is None:
        raise AppError("EMAIL_NOT_VERIFIED", "Bạn cần xác nhận email trước khi đăng nhập", 403)
    return await issue_tokens(db, user)


async def refresh(db: AsyncSession, raw: str) -> tuple[str, str]:
    token = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)).with_for_update()
    )
    if token is None:
        raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
    if token.revoked_at is not None:
        # Token đã bị xoay mà vẫn có người dùng lại, coi như bị đánh cắp: thu hồi toàn bộ phiên của user.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await db.commit()
        raise AppError("TOKEN_REUSED", "Phiên đăng nhập đã bị thu hồi, vui lòng đăng nhập lại", 401)
    if token.expires_at <= utcnow():
        raise AppError("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn", 401)
    user = await db.get(User, token.user_id)
    if user is None or user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    token.revoked_at = utcnow()
    return await issue_tokens(db, user)


async def logout(db: AsyncSession, raw: str) -> None:
    token = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)))
    if token is not None and token.revoked_at is None:
        token.revoked_at = utcnow()
        await db.commit()


async def create_admin(db: AsyncSession, email: str, password: str, full_name: str = "Quản trị viên") -> User:
    email = email.lower()
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=Role.admin,
            email_verified_at=utcnow(),  # admin tạo bằng script: coi như đã xác nhận
        )
        db.add(user)
    else:
        user.role = Role.admin
        user.password_hash = hash_password(password)
        user.email_verified_at = user.email_verified_at or utcnow()
    await db.commit()
    return user


async def approve_teacher(db: AsyncSession, email: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower(), User.role == Role.teacher))
    if user is None:
        raise AppError("NOT_FOUND", "Không tìm thấy giảng viên", 404)
    user.teacher_status = TeacherStatus.approved
    await db.commit()
    return user


# ---------- xác nhận email ----------


async def _issue_verify_token(db: AsyncSession, user: User) -> None:
    """Hủy các link cũ chưa dùng, tạo link mới và đưa email vào outbox (cùng transaction với nơi gọi)."""
    s = get_settings()
    await db.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user.id, EmailToken.purpose == VERIFY, EmailToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    raw, hashed = new_refresh_token()
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=VERIFY,
            token_hash=hashed,
            expires_at=utcnow() + timedelta(hours=s.verify_token_hours),
        )
    )
    url = f"{s.app_base_url}/verify-email?token={raw}"
    queue_email(db, user.email, VERIFY, templates.verify_email(user.full_name, url, s.verify_token_hours))


async def notify_admins_pending_teacher(db: AsyncSession, teacher: User) -> None:
    url = f"{get_settings().app_base_url}/admin/users?tab=pending"
    admins = (await db.scalars(select(User).where(User.role == Role.admin, User.locked_at.is_(None)))).all()
    for admin in admins:
        queue_email(
            db,
            admin.email,
            "new_pending_teacher",
            templates.new_pending_teacher(teacher.full_name, teacher.email, url),
        )


async def verify_email(db: AsyncSession, raw: str) -> User:
    token = await db.scalar(
        select(EmailToken)
        .where(EmailToken.token_hash == hash_refresh_token(raw), EmailToken.purpose == VERIFY)
        .with_for_update()
    )
    invalid = AppError("INVALID_TOKEN", "Link xác nhận không hợp lệ hoặc đã được thay bằng link mới", 400)
    if token is None:
        raise invalid
    user = await db.get(User, token.user_id)
    if token.used_at is not None:
        # Bấm lại link đã dùng (vd. mở mail lần 2): đã xác nhận rồi thì coi như thành công.
        if user is not None and user.email_verified_at is not None:
            return user
        raise invalid
    if token.expires_at <= utcnow():
        raise AppError("TOKEN_EXPIRED", "Link xác nhận đã hết hạn, hãy gửi lại email xác nhận", 400)
    token.used_at = utcnow()
    user.email_verified_at = utcnow()
    # chỉ báo admin khi email đã thật; tắt bắt buộc xác nhận thì đã báo lúc đăng ký rồi
    required = get_settings().email_verification_required
    if required and user.role == Role.teacher and user.teacher_status == TeacherStatus.pending:
        await notify_admins_pending_teacher(db, user)
    await db.commit()
    return user


async def resend_verification(db: AsyncSession, email: str) -> bool:
    """Trả True nếu có gửi. API luôn trả 202 để không lộ email nào đã đăng ký."""
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None or user.email_verified_at is not None or user.locked_at is not None:
        return False
    await _issue_verify_token(db, user)
    await db.commit()
    return True


async def request_teacher_review(db: AsyncSession, user: User) -> User:
    """Giảng viên bị từ chối gửi lại yêu cầu duyệt: quay về hàng chờ, xóa lý do cũ, báo admin."""
    if user.role != Role.teacher or user.teacher_status != TeacherStatus.rejected:
        raise AppError("NOT_REJECTED", "Chỉ gửi lại được khi yêu cầu giảng dạy đã bị từ chối", 409)
    user.teacher_status = TeacherStatus.pending
    user.review_note = None
    await notify_admins_pending_teacher(db, user)
    await db.commit()
    return user
