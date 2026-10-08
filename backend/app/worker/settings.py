from typing import ClassVar

from arq import cron, func
from arq.connections import RedisSettings

from app.ai.embedder import get_embedder
from app.ai.llm import get_llm_provider
from app.ai.llm_client import LLMClient
from app.ai.vision import get_vision
from app.core.config import get_settings
from app.core.storage import MinioStorage
from app.modules.notify.mailer import SmtpMailer
from app.worker.tasks import (
    JOB_TIMEOUTS,
    ingest_pdf,
    notes_synth,
    quiz_gen,
    send_pending_emails,
    source_guide,
    studio_gen,
    sweep_stale_jobs,
)


async def startup(ctx: dict) -> None:
    s = get_settings()
    storage = MinioStorage(s)
    await storage.ensure_bucket()  # API cũng tạo bucket lúc khởi động; ensure_bucket chịu được race
    ctx["storage"] = storage
    ctx["embedder"] = get_embedder(s)
    ctx["vision"] = get_vision(s)
    ctx["llm"] = LLMClient(get_llm_provider(s), s)
    ctx["mailer"] = SmtpMailer(s)


class WorkerSettings:
    # Tên hàm = job.type. timeout riêng cho từng loại job (spec K4)
    functions: ClassVar = [
        func(ingest_pdf, name="ingest_pdf", timeout=JOB_TIMEOUTS["ingest_pdf"]),
        func(quiz_gen, name="quiz_gen", timeout=JOB_TIMEOUTS["quiz_gen"]),
        func(send_pending_emails, name="send_pending_emails", timeout=120),
        func(source_guide, name="source_guide", timeout=JOB_TIMEOUTS["source_guide"]),
        func(studio_gen, name="studio_gen", timeout=JOB_TIMEOUTS["studio_gen"]),
        func(notes_synth, name="notes_synth", timeout=JOB_TIMEOUTS["notes_synth"]),
    ]
    # 5 phút một lần: job processing quá timeout + 5 phút → failed "Worker bị gián đoạn";
    # job pending bị kẹt → enqueue lại một lần, vẫn kẹt → failed "Không đưa được job vào hàng đợi"
    cron_jobs: ClassVar = [
        cron(
            sweep_stale_jobs,
            name="sweep_stale_jobs",
            minute=set(range(0, 60, 5)),
            run_at_startup=True,
            timeout=60,
        ),
        # Vét email còn trong outbox (kick từ API bị lỡ, SMTP lỗi cần thử lại)
        cron(
            send_pending_emails,
            name="send_pending_emails_cron",
            minute=set(range(60)),
            run_at_startup=True,
            timeout=120,
        ),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 5
