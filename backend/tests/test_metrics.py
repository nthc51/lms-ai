import uuid

from prometheus_client import REGISTRY

from app.ai.models import AiCall
from app.core.metrics import refresh_business_metrics
from app.core.time import utcnow
from app.modules.jobs.models import Job, JobStatus
from app.modules.notify.models import EmailOutbox, EmailStatus


async def test_metrics_endpoint_exposes_http_metrics(client):
    await client.get("/api/v1/courses")
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text
    assert 'handler="/api/v1/courses"' in r.text
    assert "lms_jobs" in r.text


async def test_metrics_endpoint_is_hidden_from_openapi(client):
    assert "/metrics" not in (await client.get("/openapi.json")).json()["paths"]


def _mail(status: EmailStatus) -> EmailOutbox:
    return EmailOutbox(
        to_email="a@x.com", subject="s", body_text="t", body_html="h", template="verify_email", status=status
    )


async def test_business_metrics_count_jobs_emails_and_ai_tokens(db):
    db.add_all(
        [
            Job(type="ingest_pdf", ref_id=uuid.uuid4(), status=JobStatus.pending),
            Job(type="ingest_pdf", ref_id=uuid.uuid4(), status=JobStatus.pending),
            Job(type="studio_gen", ref_id=uuid.uuid4(), status=JobStatus.processing),
            Job(type="ingest_pdf", ref_id=uuid.uuid4(), status=JobStatus.failed, finished_at=utcnow()),
            Job(type="ingest_pdf", ref_id=uuid.uuid4(), status=JobStatus.done, finished_at=utcnow()),
            _mail(EmailStatus.pending),
            _mail(EmailStatus.failed),
            _mail(EmailStatus.sent),
            AiCall(
                op="tutor_answer",
                provider="fake",
                model="m",
                prompt_version="v1",
                status="ok",
                tokens_in=100,
                tokens_out=20,
            ),
            AiCall(
                op="tutor_answer",
                provider="fake",
                model="m",
                prompt_version="v1",
                status="ok",
                tokens_in=50,
                tokens_out=5,
            ),
        ]
    )
    await db.commit()
    await refresh_business_metrics(db)

    def val(name, **labels):
        return REGISTRY.get_sample_value(name, labels)

    assert val("lms_jobs", type="ingest_pdf", status="pending") == 2
    assert val("lms_jobs", type="studio_gen", status="processing") == 1
    assert val("lms_jobs", type="ingest_pdf", status="failed_1h") == 1
    assert (
        val("lms_jobs", type="ingest_pdf", status="done") is None
    )  # job đã xong không phải việc cần theo dõi
    assert val("lms_tutor_ttft_p95_ms") == 0  # chưa có tin nhắn Tutor nào
    assert val("lms_email_outbox", status="pending") == 1
    assert val("lms_email_outbox", status="failed_24h") == 1
    assert val("lms_ai_tokens_1h", op="tutor_answer", direction="in") == 150
    assert val("lms_ai_tokens_1h", op="tutor_answer", direction="out") == 25
