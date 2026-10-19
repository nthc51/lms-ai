import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.pagination import Page


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str
    read: bool
    created_at: datetime


class NotificationPage(Page[NotificationOut]):
    unread: int  # số chưa đọc (cả những cái không nằm trong trang này)


class UnreadOut(BaseModel):
    unread: int
