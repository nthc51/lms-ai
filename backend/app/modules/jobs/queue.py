from functools import lru_cache
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.modules.jobs.models import Job


class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> None: ...


class ArqQueue:
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def enqueue(self, job: Job) -> None:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
        # Tên hàm trong worker trùng với job.type; _job_id giúp arq tự bỏ qua nếu enqueue trùng
        await self._pool.enqueue_job(job.type, str(job.id), _job_id=str(job.id))


@lru_cache
def get_queue() -> JobQueue:
    return ArqQueue(get_settings().redis_url)
