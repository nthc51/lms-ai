import uuid

import filetype
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_staff
from app.core.errors import AppError, not_found
from app.core.storage import Storage, staging_key
from app.core.time import utcnow
from app.modules.auth.models import Role, User
from app.modules.materials.models import Asset, AssetKind
from app.modules.materials.schemas import PresignIn, PresignOut

MB = 1024 * 1024
SIZE_LIMITS = {
    AssetKind.pdf: 50 * MB,
    AssetKind.video: 500 * MB,
    AssetKind.submission: 20 * MB,
    AssetKind.image: 5 * MB,
}
ALLOWED_MIME = {
    AssetKind.pdf: {"application/pdf"},
    AssetKind.video: {"video/mp4"},
    AssetKind.submission: {"application/pdf", "text/plain"},
    AssetKind.image: {"image/png", "image/jpeg", "image/webp"},
}
STAFF_ONLY_KINDS = {AssetKind.pdf, AssetKind.video}  # tài liệu và video bài học chỉ giảng viên/admin upload
EXTENSIONS = {
    "application/pdf": "pdf",
    "video/mp4": "mp4",
    "text/plain": "txt",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def _too_large() -> AppError:
    return AppError("FILE_TOO_LARGE", "File vượt quá dung lượng cho phép", 413)


def _invalid_type() -> AppError:
    return AppError("INVALID_FILE_TYPE", "Định dạng file không hợp lệ", 400)


def mime_matches(declared: str, head: bytes) -> bool:
    """So magic bytes của 2KB đầu với mime đã khai báo. Text thuần thì không có magic bytes."""
    guessed = filetype.guess(head)
    if declared == "text/plain":
        return guessed is None and b"\x00" not in head
    return guessed is not None and guessed.mime == declared


async def create_presigned_upload(
    db: AsyncSession, storage: Storage, user: User, data: PresignIn
) -> PresignOut:
    kind = AssetKind(data.kind)
    if kind in STAFF_ONLY_KINDS:
        await require_staff(user)
    if data.mime not in ALLOWED_MIME[kind]:
        raise _invalid_type()
    if data.size > SIZE_LIMITS[kind]:
        raise _too_large()
    key = f"{kind.value}/{user.id}/{uuid.uuid4().hex}.{EXTENSIONS[data.mime]}"
    asset = Asset(owner_id=user.id, kind=kind, storage_key=key, mime=data.mime, size_bytes=0)
    db.add(asset)
    await db.commit()
    # Trình duyệt chỉ nhận URL ghi vào key tạm; key chính thức chỉ có server ghi sau khi kiểm tra xong.
    return PresignOut(asset_id=asset.id, put_url=await storage.presign_put(staging_key(key)))


async def complete_upload(db: AsyncSession, storage: Storage, user: User, asset_id: uuid.UUID) -> Asset:
    # Khóa dòng asset để các lần complete đồng thời chạy tuần tự
    asset = await db.get(Asset, asset_id, with_for_update=True)
    if asset is None or asset.owner_id != user.id:
        raise not_found("File")
    if asset.verified_at is not None:
        return asset
    staged = staging_key(asset.storage_key)
    size = await storage.stat_size(staged)
    if size is None:
        raise AppError("UPLOAD_MISSING", "Chưa tìm thấy file đã upload", 400)

    async def reject(err: AppError, *keys: str) -> None:
        for key in keys:
            await storage.remove(key)
        await db.delete(asset)
        await db.commit()
        raise err

    limit = SIZE_LIMITS[asset.kind]
    if size > limit:
        await reject(_too_large(), staged)
    # Copy trước rồi mới kiểm tra bản ở key chính thức (client không ghi được vào đó): tránh việc client
    # PUT lại vào key tạm giữa lúc kiểm tra và lúc copy.
    await storage.copy(staged, asset.storage_key)
    size = await storage.stat_size(asset.storage_key)
    if size is None or size > limit:
        await reject(_too_large(), staged, asset.storage_key)
    if not mime_matches(asset.mime, await storage.read_head(asset.storage_key)):
        await reject(_invalid_type(), staged, asset.storage_key)
    asset.size_bytes = size
    asset.verified_at = utcnow()
    await db.commit()
    # Xóa key tạm sau khi commit: nếu commit lỗi thì vẫn còn file tạm để complete lại
    await storage.remove(staged)
    return asset


async def require_verified_asset(db: AsyncSession, asset_id: uuid.UUID, user: User, kind: AssetKind) -> Asset:
    asset = await db.get(Asset, asset_id)
    if (
        asset is None
        or asset.kind != kind
        or asset.verified_at is None
        or (asset.owner_id != user.id and user.role != Role.admin)
    ):
        raise AppError("INVALID_ASSET", "File không hợp lệ hoặc chưa upload xong", 400)
    return asset
