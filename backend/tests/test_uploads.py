import pytest

from app.core.storage import STAGING_PREFIX
from tests.helpers import API, make_published_course, make_student, make_teacher

PDF = b"%PDF-1.7\n" + b"0" * 100
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
EXE = b"MZ\x90\x00" + b"\x00" * 100
MB = 1024 * 1024


async def _presign(client, headers, kind="pdf", mime="application/pdf", size=1000):
    return await client.post(
        f"{API}/uploads/presign", json={"kind": kind, "mime": mime, "size": size}, headers=headers
    )


def _staging(presign_response) -> str:
    """Key mà URL presign cho phép PUT (luôn là key tạm)."""
    return presign_response.json()["put_url"].removeprefix("memory://put/")


def _final(presign_response) -> str:
    return _staging(presign_response).removeprefix(STAGING_PREFIX)


async def _complete(client, presign_response, headers):
    return await client.post(f"{API}/uploads/{presign_response.json()['asset_id']}/complete", headers=headers)


async def _upload(client, storage, headers, data, kind="pdf", mime="application/pdf"):
    r = await _presign(client, headers, kind, mime, len(data))
    assert r.status_code == 200, r.text
    storage.client_put(r.json()["put_url"], data, mime)
    return r, await _complete(client, r, headers)


async def test_presign_returns_staging_url_and_asset(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv)
    assert r.status_code == 200
    assert (
        r.json()["asset_id"]
        and _staging(r).startswith(f"{STAGING_PREFIX}pdf/")
        and _final(r).endswith(".pdf")
    )


async def test_presign_rejects_mime_not_allowed_for_kind(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv, kind="pdf", mime="image/png")
    assert (r.status_code, r.json()["error"]["code"]) == (400, "INVALID_FILE_TYPE")


async def test_presign_rejects_declared_size_over_limit(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv, size=60 * MB)
    assert (r.status_code, r.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


@pytest.mark.parametrize(
    ("kind", "mime", "limit"), [("pdf", "application/pdf", 50 * MB), ("video", "video/mp4", 500 * MB)]
)
async def test_presign_declared_size_boundary(client, kind, mime, limit):
    _, gv = await make_teacher(client)
    assert (await _presign(client, gv, kind, mime, size=limit)).status_code == 200
    over = await _presign(client, gv, kind, mime, size=limit + 1)
    assert (over.status_code, over.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


async def test_submission_declared_size_boundary(client):
    _, sv = await make_student(client)
    assert (await _presign(client, sv, "submission", "text/plain", size=20 * MB)).status_code == 200
    over = await _presign(client, sv, "submission", "text/plain", size=20 * MB + 1)
    assert (over.status_code, over.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


@pytest.mark.parametrize(("kind", "mime"), [("pdf", "application/pdf"), ("video", "video/mp4")])
async def test_student_cannot_presign_course_material(client, kind, mime):
    _, sv = await make_student(client)
    r = await _presign(client, sv, kind, mime)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")


async def test_complete_without_upload(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv)
    done = await _complete(client, r, gv)
    assert (done.status_code, done.json()["error"]["code"]) == (400, "UPLOAD_MISSING")


async def test_complete_valid_pdf_moves_staging_to_final(client, storage):
    _, gv = await make_teacher(client)
    r, done = await _upload(client, storage, gv, PDF)
    assert done.status_code == 200
    assert done.json()["verified_at"] is not None and done.json()["size_bytes"] == len(PDF)
    assert _staging(r) not in storage.objects
    assert storage.objects[_final(r)] == PDF and storage.mimes[_final(r)] == "application/pdf"


async def test_reput_after_verify_cannot_touch_final_object(client, storage):
    _, gv = await make_teacher(client)
    r, done = await _upload(client, storage, gv, PDF)
    assert done.status_code == 200
    # URL presign chỉ trỏ vào key tạm: PUT lại (ví dụ thay bằng file .exe) không chạm tới key chính thức
    assert r.json()["put_url"].startswith(f"memory://put/{STAGING_PREFIX}")
    storage.client_put(r.json()["put_url"], EXE, "application/pdf")
    again = await _complete(client, r, gv)
    assert again.status_code == 200 and again.json()["verified_at"] == done.json()["verified_at"]
    assert storage.objects[_final(r)] == PDF


async def test_reput_during_complete_is_verified_on_final_copy(client, storage):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv, size=len(PDF))
    storage.client_put(r.json()["put_url"], PDF, "application/pdf")
    # client đổi file ở key tạm ngay sau lúc stat, trước lúc copy
    storage.on_copy = lambda: storage.client_put(r.json()["put_url"], EXE, "application/pdf")
    done = await _complete(client, r, gv)
    assert (done.status_code, done.json()["error"]["code"]) == (400, "INVALID_FILE_TYPE")
    assert _staging(r) not in storage.objects and _final(r) not in storage.objects


async def test_complete_rejects_renamed_executable(client, storage):
    _, gv = await make_teacher(client)
    r, done = await _upload(client, storage, gv, EXE)
    assert (done.status_code, done.json()["error"]["code"]) == (400, "INVALID_FILE_TYPE")
    assert _staging(r) not in storage.objects and _final(r) not in storage.objects
    assert (await _complete(client, r, gv)).status_code == 404


async def test_complete_rejects_actual_size_over_limit(client, storage):
    _, sv = await make_student(client)
    big = b"a" * (20 * MB + 1)
    r = await _presign(client, sv, kind="submission", mime="text/plain", size=100)
    storage.client_put(r.json()["put_url"], big, "text/plain")
    done = await _complete(client, r, sv)
    assert (done.status_code, done.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")
    assert _staging(r) not in storage.objects and _final(r) not in storage.objects
    assert (await _complete(client, r, sv)).status_code == 404


async def test_other_user_cannot_complete(client, storage):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    r = await _presign(client, gv)
    storage.client_put(r.json()["put_url"], PDF, "application/pdf")
    done = await _complete(client, r, sv)
    assert done.status_code == 404


async def test_attach_video_and_stream_url(client, storage):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    r, done = await _upload(client, storage, gv, MP4, kind="video", mime="video/mp4")
    assert done.status_code == 200
    patch = await client.patch(
        f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]}, headers=gv
    )
    assert patch.status_code == 200 and patch.json()["video_asset_id"] == r.json()["asset_id"]

    denied = await client.get(f"{API}/lessons/{lesson['id']}/video", headers=sv)
    assert denied.status_code == 403
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    ok = await client.get(f"{API}/lessons/{lesson['id']}/video", headers=sv)
    assert ok.status_code == 200 and ok.json()["url"] == f"memory://get/{_final(r)}"
    assert storage.signed_gets[_final(r)] == {"response-content-type": "video/mp4"}


async def test_patch_null_detaches_video_and_omission_keeps_it(client, storage):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r, _ = await _upload(client, storage, gv, MP4, kind="video", mime="video/mp4")
    asset_id = r.json()["asset_id"]
    url = f"{API}/lessons/{lesson['id']}"
    await client.patch(url, json={"video_asset_id": asset_id, "duration_sec": 90}, headers=gv)

    kept = await client.patch(url, json={"title": "Bài 1 (sửa)"}, headers=gv)
    assert kept.status_code == 200
    assert (kept.json()["video_asset_id"], kept.json()["duration_sec"]) == (asset_id, 90)

    # null ở trường bắt buộc (title) vẫn bị bỏ qua như trước
    ignored = await client.patch(url, json={"title": None}, headers=gv)
    assert ignored.status_code == 200 and ignored.json()["title"] == "Bài 1 (sửa)"

    detached = await client.patch(url, json={"video_asset_id": None}, headers=gv)
    assert detached.status_code == 200
    assert detached.json()["video_asset_id"] is None and detached.json()["duration_sec"] == 90
    assert (await client.get(f"{API}/lessons/{lesson['id']}/video", headers=gv)).status_code == 404


async def test_attach_pdf_as_video_is_rejected(client, storage):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r, _ = await _upload(client, storage, gv, PDF)
    patch = await client.patch(
        f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]}, headers=gv
    )
    assert (patch.status_code, patch.json()["error"]["code"]) == (400, "INVALID_ASSET")


async def test_attach_other_teachers_video_is_rejected(client, storage):
    _, gv = await make_teacher(client)
    _, gv2 = await make_teacher(client, email="gv2@x.com")
    _, _, lesson = await make_published_course(client, gv)
    r, done = await _upload(client, storage, gv2, MP4, kind="video", mime="video/mp4")
    assert done.status_code == 200
    patch = await client.patch(
        f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]}, headers=gv
    )
    assert (patch.status_code, patch.json()["error"]["code"]) == (400, "INVALID_ASSET")


async def test_attach_unverified_video_is_rejected(client):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r = await _presign(client, gv, kind="video", mime="video/mp4")
    patch = await client.patch(
        f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]}, headers=gv
    )
    assert (patch.status_code, patch.json()["error"]["code"]) == (400, "INVALID_ASSET")


async def test_student_cannot_patch_lesson(client, storage):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    r, _ = await _upload(client, storage, gv, MP4, kind="video", mime="video/mp4")
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    patch = await client.patch(
        f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]}, headers=sv
    )
    assert (patch.status_code, patch.json()["error"]["code"]) == (403, "FORBIDDEN")
