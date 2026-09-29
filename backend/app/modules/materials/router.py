import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.core.storage import Storage, get_storage
from app.modules.auth.models import User
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.materials import assets
from app.modules.materials.models import Asset
from app.modules.materials.schemas import AssetOut, PresignIn, PresignOut, UrlOut

router = APIRouter(prefix="/api/v1", tags=["materials"])


@router.post("/uploads/presign", response_model=PresignOut)
async def presign(data: PresignIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                  storage: Storage = Depends(get_storage)):
    return await assets.create_presigned_upload(db, storage, user, data)


@router.post("/uploads/{asset_id}/complete", response_model=AssetOut)
async def complete(asset_id: uuid.UUID, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db), storage: Storage = Depends(get_storage)):
    return await assets.complete_upload(db, storage, user, asset_id)


@router.get("/lessons/{lesson_id}/video", response_model=UrlOut)
async def lesson_video(lesson_id: uuid.UUID, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db), storage: Storage = Depends(get_storage)):
    lesson, _ = await ensure_lesson_access(db, lesson_id, user)
    asset = await db.get(Asset, lesson.video_asset_id) if lesson.video_asset_id else None
    if asset is None:
        raise not_found("Video")
    return UrlOut(url=await storage.presign_get(asset.storage_key))
