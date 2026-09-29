import uuid

from app.ai.embedder import FakeEmbedder
from app.ai.vision import FakeVision
from app.ingestion.pipeline import ingest_pdf_source
from app.modules.materials.models import ExtractionMethod, Source, SourcePage, SourceStatus
from tests.helpers import API, make_published_course, make_student, make_teacher, upload_file
from tests.pdfs import LONG_TEXT, make_pdf


async def _attach(client, headers, lesson_id, asset_id):
    return await client.post(f"{API}/lessons/{lesson_id}/sources", json={"asset_id": asset_id}, headers=headers)


async def _attached_source(client, storage, headers) -> tuple[dict, str]:
    _, _, lesson = await make_published_course(client, headers)
    asset_id = await upload_file(client, storage, headers, make_pdf([LONG_TEXT]))
    r = await _attach(client, headers, lesson["id"], asset_id)
    assert r.status_code == 202, r.text
    return lesson, r.json()["source"]["id"]


async def test_teacher_attaches_pdf_and_job_is_enqueued(client, storage, queue):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    asset_id = await upload_file(client, storage, gv, make_pdf([LONG_TEXT]))
    r = await _attach(client, gv, lesson["id"], asset_id)
    assert r.status_code == 202
    body = r.json()
    assert body["source"]["status"] == "pending"
    assert body["source"]["vision_pages"] == 0 and body["source"]["warning"] is None
    assert queue.jobs == [("ingest_pdf", uuid.UUID(body["source"]["id"]))]
    job = await client.get(f"{API}/jobs/{body['job_id']}", headers=gv)
    assert job.json()["status"] == "pending"
    listed = await client.get(f"{API}/lessons/{lesson['id']}/sources", headers=gv)
    assert [s["id"] for s in listed.json()] == [body["source"]["id"]]


async def test_student_and_other_teacher_cannot_attach(client, storage):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, sv = await make_student(client)
    _, _, lesson = await make_published_course(client, gv1)
    asset_id = await upload_file(client, storage, gv1, make_pdf([LONG_TEXT]))
    r_sv = await _attach(client, sv, lesson["id"], asset_id)
    r_gv2 = await _attach(client, gv2, lesson["id"], asset_id)
    assert (r_sv.status_code, r_sv.json()["error"]["code"]) == (403, "FORBIDDEN")
    assert r_gv2.status_code == 404


async def test_other_teacher_gets_404_on_source_endpoints(client, storage):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    lesson, source_id = await _attached_source(client, storage, gv1)
    for r in (await client.get(f"{API}/sources/{source_id}", headers=gv2),
              await client.get(f"{API}/sources/{source_id}/pages", headers=gv2),
              await client.post(f"{API}/sources/{source_id}/reprocess", headers=gv2),
              await client.get(f"{API}/lessons/{lesson['id']}/sources", headers=gv2)):
        assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


async def test_unverified_asset_is_rejected(client):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r = await client.post(f"{API}/uploads/presign", json={"kind": "pdf", "mime": "application/pdf", "size": 10},
                          headers=gv)
    attach = await _attach(client, gv, lesson["id"], r.json()["asset_id"])
    assert (attach.status_code, attach.json()["error"]["code"]) == (400, "INVALID_ASSET")


async def test_reprocess_only_when_finished(client, storage, queue, db):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    asset_id = await upload_file(client, storage, gv, make_pdf([LONG_TEXT]))
    source_id = (await _attach(client, gv, lesson["id"], asset_id)).json()["source"]["id"]

    busy = await client.post(f"{API}/sources/{source_id}/reprocess", headers=gv)
    assert (busy.status_code, busy.json()["error"]["code"]) == (409, "INVALID_STATE")

    src = await db.get(Source, uuid.UUID(source_id))
    src.status = SourceStatus.failed
    await db.commit()
    # job đầu vẫn 'pending' trong bảng jobs; đánh dấu xong để partial unique index cho tạo job mới
    from sqlalchemy import update

    from app.modules.jobs.models import Job, JobStatus
    await db.execute(update(Job).values(status=JobStatus.failed))
    await db.commit()

    ok = await client.post(f"{API}/sources/{source_id}/reprocess", headers=gv)
    assert ok.status_code == 202 and len(queue.jobs) == 2
    detail = (await client.get(f"{API}/sources/{source_id}", headers=gv)).json()
    assert detail["status"] == "pending" and detail["error_msg"] is None


async def test_pages_and_counts_after_processing(client, storage):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    asset_id = await upload_file(client, storage, gv, make_pdf([LONG_TEXT, ""]))
    source_id = (await _attach(client, gv, lesson["id"], asset_id)).json()["source"]["id"]

    await ingest_pdf_source(uuid.UUID(source_id), storage=storage, embedder=FakeEmbedder(768), vision=FakeVision())

    detail = (await client.get(f"{API}/sources/{source_id}", headers=gv)).json()
    assert detail["status"] == "ready" and detail["page_count"] == 2 and detail["chunk_count"] >= 1
    assert detail["vision_pages"] == 1 and detail["warning"] is None
    pages = (await client.get(f"{API}/sources/{source_id}/pages", headers=gv)).json()
    assert [p["extraction_method"] for p in pages] == ["text", "vision"]


async def test_vision_pages_counted_per_source_in_detail_and_list(client, storage, db):
    _, gv = await make_teacher(client)
    lesson, first_id = await _attached_source(client, storage, gv)
    asset_id = await upload_file(client, storage, gv, make_pdf([LONG_TEXT]))
    second_id = (await _attach(client, gv, lesson["id"], asset_id)).json()["source"]["id"]
    methods = [ExtractionMethod.vision, ExtractionMethod.text, ExtractionMethod.vision]
    db.add_all([SourcePage(source_id=uuid.UUID(first_id), page_no=i + 1, extraction_method=m, markdown="x")
                for i, m in enumerate(methods)])
    db.add(SourcePage(source_id=uuid.UUID(second_id), page_no=1, extraction_method=ExtractionMethod.text,
                      markdown="y"))
    await db.commit()

    detail = (await client.get(f"{API}/sources/{first_id}", headers=gv)).json()
    assert (detail["page_count"], detail["vision_pages"]) == (3, 2)
    listed = (await client.get(f"{API}/lessons/{lesson['id']}/sources", headers=gv)).json()
    stats = [(s["id"], s["page_count"], s["vision_pages"]) for s in listed]
    assert stats == [(first_id, 3, 2), (second_id, 1, 0)]


async def test_failed_source_has_error_but_no_warning(client, storage, db):
    _, gv = await make_teacher(client)
    lesson, source_id = await _attached_source(client, storage, gv)
    src = await db.get(Source, uuid.UUID(source_id))
    src.status, src.error_msg = SourceStatus.failed, "Tài liệu không có nội dung đọc được"
    await db.commit()

    detail = (await client.get(f"{API}/sources/{source_id}", headers=gv)).json()
    assert detail["status"] == "failed"
    assert detail["error_msg"] == "Tài liệu không có nội dung đọc được" and detail["warning"] is None
    listed = (await client.get(f"{API}/lessons/{lesson['id']}/sources", headers=gv)).json()
    assert listed[0]["warning"] is None


async def test_ready_source_with_vision_cap_exposes_warning(client, storage):
    _, gv = await make_teacher(client)
    lesson, _ = await _attached_source(client, storage, gv)
    asset_id = await upload_file(client, storage, gv, make_pdf(["", ""]))
    source_id = (await _attach(client, gv, lesson["id"], asset_id)).json()["source"]["id"]

    await ingest_pdf_source(uuid.UUID(source_id), storage=storage, embedder=FakeEmbedder(768),
                            vision=FakeVision(), max_vision_pages=1)

    detail = (await client.get(f"{API}/sources/{source_id}", headers=gv)).json()
    assert detail["status"] == "ready" and detail["vision_pages"] == 1
    assert detail["warning"] and detail["warning"] == detail["error_msg"]
    listed = (await client.get(f"{API}/lessons/{lesson['id']}/sources", headers=gv)).json()
    listed = {s["id"]: s for s in listed}
    assert listed[source_id]["warning"] == detail["warning"]
