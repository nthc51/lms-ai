"""Metrics cho Prometheus (spec tầng S4).

- HTTP: prometheus-fastapi-instrumentator (http_requests_total, http_request_duration_*).
- Nghiệp vụ, lấy từ DB mỗi `metrics_refresh_s` giây:
  - số job đang chờ / đang chạy / lỗi trong 1 giờ (gồm cả job AI Studio),
  - p95 thời gian tới token đầu của AI Tutor,
  - số email đang chờ gửi và email lỗi hẳn trong 24 giờ (hộp thư đi),
  - token AI 1 giờ gần nhất (bảng ai_calls).
"""

import asyncio
import logging

from fastapi import FastAPI
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal

logger = logging.getLogger(__name__)

# Tạo MỘT lần cho cả tiến trình: test gọi create_app() nhiều lần, tạo lại sẽ trùng tên metric
_HTTP_METRICS = metrics.default()

JOBS = Gauge(
    "lms_jobs", "Số job theo loại và trạng thái (failed_1h: lỗi trong 1 giờ gần nhất)", ["type", "status"]
)
TUTOR_TTFT_P95 = Gauge(
    "lms_tutor_ttft_p95_ms", "p95 thời gian tới token đầu tiên của AI Tutor, 15 phút gần nhất"
)
EMAILS = Gauge(
    "lms_email_outbox",
    "Email trong hộp thư đi (pending: chờ gửi, failed_24h: lỗi hẳn, tạo trong 24 giờ)",
    ["status"],
)
AI_TOKENS = Gauge(
    "lms_ai_tokens_1h", "Token AI 1 giờ gần nhất theo loại tác vụ và chiều (in/out)", ["op", "direction"]
)

_EXCLUDED = ["/metrics", "/api/v1/health", "/api/v1/ready"]


def setup_metrics(app: FastAPI) -> None:
    Instrumentator(excluded_handlers=_EXCLUDED).add(_HTTP_METRICS).instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )


async def refresh_business_metrics(db: AsyncSession) -> None:
    rows = (
        await db.execute(
            text(
                """
                SELECT type, CASE WHEN status = 'failed' THEN 'failed_1h' ELSE status::text END, count(*)
                FROM jobs
                WHERE status IN ('pending', 'processing')
                   OR (status = 'failed' AND finished_at > now() - interval '1 hour')
                GROUP BY 1, 2
                """
            )
        )
    ).all()
    JOBS.clear()  # xóa nhãn cũ: loại job đã hết việc thì không còn treo số liệu cũ
    for type_, status, count in rows:
        JOBS.labels(type=type_, status=status).set(count)

    p95 = await db.scalar(
        text(
            """
            SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY ttft_ms)
            FROM chat_messages
            WHERE role = 'assistant' AND ttft_ms IS NOT NULL AND created_at > now() - interval '15 minutes'
            """
        )
    )
    TUTOR_TTFT_P95.set(p95 or 0)

    pending, failed = (
        await db.execute(
            text(
                """
                SELECT count(*) FILTER (WHERE status = 'pending'),
                       count(*) FILTER (WHERE status = 'failed' AND created_at > now() - interval '1 day')
                FROM email_outbox
                """
            )
        )
    ).one()
    EMAILS.labels(status="pending").set(pending)
    EMAILS.labels(status="failed_24h").set(failed)

    tokens = (
        await db.execute(
            text(
                """
                SELECT op, coalesce(sum(tokens_in), 0), coalesce(sum(tokens_out), 0)
                FROM ai_calls
                WHERE created_at > now() - interval '1 hour'
                GROUP BY op
                """
            )
        )
    ).all()
    AI_TOKENS.clear()
    for op, t_in, t_out in tokens:
        AI_TOKENS.labels(op=op, direction="in").set(t_in)
        AI_TOKENS.labels(op=op, direction="out").set(t_out)


async def metrics_refresher(interval_s: int) -> None:
    while True:
        try:
            async with SessionLocal() as db:
                await refresh_business_metrics(db)
        except Exception:  # lỗi đo đạc không được làm sập API
            logger.exception("Không cập nhật được metrics nghiệp vụ")
        await asyncio.sleep(interval_s)
