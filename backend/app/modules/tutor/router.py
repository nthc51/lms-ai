import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedder import Embedder, get_api_embedder
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.pagination import PageParams, page_params
from app.modules.auth.models import User
from app.modules.tutor import service
from app.modules.tutor.schemas import AvailabilityOut, MessagePage, SessionCreate, SessionOut, SessionPage

router = APIRouter(prefix="/api/v1", tags=["tutor"])


@router.post("/tutor/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    data: SessionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.create_session(db, user, data)


@router.get("/tutor/sessions", response_model=SessionPage)
async def list_sessions(
    course_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_sessions(db, user, course_id, params)


@router.get("/tutor/availability", response_model=AvailabilityOut)
async def availability(
    course_id: uuid.UUID,
    lesson_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    embedder: Embedder = Depends(get_api_embedder),
):
    return await service.availability(db, user, course_id, lesson_id, embedder.model)


@router.get("/tutor/sessions/{session_id}/messages", response_model=MessagePage)
async def list_messages(
    session_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await service.get_own_session(db, session_id, user)
    return await service.list_messages(db, session, params)
