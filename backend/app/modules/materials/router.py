import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_staff
from app.core.errors import not_found
from app.core.storage import Storage, get_storage
from app.modules.auth.models import User
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.jobs.queue import JobQueue, get_queue
from app.modules.materials import assets, sources
from app.modules.materials.models import Asset
from app.modules.materials.schemas import (
    AssetOut,
    JobRef,
    PresignIn,
    PresignOut,
    SourceCreate,
    SourceCreated,
    SourceOut,
    SourcePagesPage,
    UrlOut,
)

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
    return UrlOut(url=await storage.presign_get(asset.storage_key, asset.mime))


@router.post("/lessons/{lesson_id}/sources", response_model=SourceCreated, status_code=202)
async def attach_source(lesson_id: uuid.UUID, data: SourceCreate, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db), queue: JobQueue = Depends(get_queue)):
    source, job = await sources.attach_pdf(db, queue, user, lesson_id, data.asset_id)
    return SourceCreated(source=await sources.to_out(db, source), job_id=job.id)


@router.get("/lessons/{lesson_id}/sources", response_model=list[SourceOut])
async def lesson_sources(lesson_id: uuid.UUID, user: User = Depends(require_staff),
                         db: AsyncSession = Depends(get_db)):
    return await sources.list_lesson_sources(db, user, lesson_id)


@router.get("/sources/{source_id}", response_model=SourceOut)
async def source_detail(source_id: uuid.UUID, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)):
    return await sources.to_out(db, await sources.get_owned_source(db, source_id, user))


@router.get("/sources/{source_id}/pages", response_model=SourcePagesPage)
async def source_pages(source_id: uuid.UUID, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                       user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)):
    return await sources.list_pages(db, await sources.get_owned_source(db, source_id, user), page, size)


@router.post("/sources/{source_id}/reprocess", response_model=JobRef, status_code=202)
async def reprocess_source(source_id: uuid.UUID, user: User = Depends(require_staff),
                           db: AsyncSession = Depends(get_db), queue: JobQueue = Depends(get_queue)):
    source = await sources.get_owned_source(db, source_id, user)
    job = await sources.reprocess(db, queue, source, user)
    return JobRef(job_id=job.id)
