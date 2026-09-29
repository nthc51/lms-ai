from typing import ClassVar

from arq import cron, func
from arq.connections import RedisSettings

from app.ai.embedder import get_embedder
from app.ai.vision import get_vision
from app.core.config import get_settings
from app.core.storage import MinioStorage
from app.worker.tasks import JOB_TIMEOUTS, ingest_pdf, sweep_stale_jobs


async def startup(ctx: dict) -> None:
    s = get_settings()
    storage = MinioStorage(s)
    await storage.ensure_bucket()  # API cũng tạo bucket lúc khởi động; ensure_bucket chịu được race
    ctx["storage"] = storage
    ctx["embedder"] = get_embedder(s)
    ctx["vision"] = get_vision(s)


class WorkerSettings:
    # Tên hàm = job.type. timeout riêng cho từng loại job (spec K4)
    functions: ClassVar = [func(ingest_pdf, name="ingest_pdf", timeout=JOB_TIMEOUTS["ingest_pdf"])]
    # 5 phút một lần: job processing quá timeout + 5 phút → failed "Worker bị gián đoạn";
    # job pending bị kẹt → enqueue lại một lần, vẫn kẹt → failed "Không đưa được job vào hàng đợi"
    cron_jobs: ClassVar = [
        cron(
            sweep_stale_jobs,
            name="sweep_stale_jobs",
            minute=set(range(0, 60, 5)),
            run_at_startup=True,
            timeout=60,
        )
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 5
