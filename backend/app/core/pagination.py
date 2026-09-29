from dataclasses import dataclass

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Trần cho query param `page`: số lớn hơn sẽ tràn int64 khi tính OFFSET → 500. Chặn ở 422.
MAX_PAGE = 10_000
MAX_SIZE = 100


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


@dataclass
class PageParams:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def page_params(
    page: int = Query(1, ge=1, le=MAX_PAGE), size: int = Query(20, ge=1, le=MAX_SIZE)
) -> PageParams:
    return PageParams(page=page, size=size)


async def paginate(db: AsyncSession, stmt: Select, params: PageParams) -> tuple[int, Select]:
    """Đếm tổng số dòng của `stmt` và trả về câu lệnh đã gắn OFFSET/LIMIT của trang yêu cầu.
    `stmt` phải có ORDER BY ổn định (kèm cột id làm tiebreaker)."""
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return total or 0, stmt.offset(params.offset).limit(params.size)
