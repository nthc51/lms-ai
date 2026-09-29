from functools import lru_cache
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.modules.jobs.models import Job


class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> None: ...


class ArqQueue:
    """Nơi duy nhất gọi arq enqueue_job. API tạo pool từ redis_url khi cần; worker (sweeper) truyền sẵn
    pool arq của nó (ctx['redis'])."""

    def __init__(self, redis_url: str | None = None, pool: ArqRedis | None = None):
        assert redis_url is not None or pool is not None
        self._redis_url = redis_url
        self._pool = pool

    async def enqueue(self, job: Job) -> None:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
        # Tên hàm trong worker trùng với job.type; _job_id giúp arq tự bỏ qua nếu enqueue trùng
        await self._pool.enqueue_job(job.type, str(job.id), _job_id=str(job.id))


@lru_cache
def get_queue() -> JobQueue:
    return ArqQueue(get_settings().redis_url)
