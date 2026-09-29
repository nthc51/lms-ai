from tests.helpers import API, make_published_course, make_student, make_teacher

PDF = b"%PDF-1.7\n" + b"0" * 100
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
EXE = b"MZ\x90\x00" + b"\x00" * 100


async def _presign(client, headers, kind="pdf", mime="application/pdf", size=1000):
    return await client.post(f"{API}/uploads/presign", json={"kind": kind, "mime": mime, "size": size},
                             headers=headers)


def _key(presign_response) -> str:
    return presign_response.json()["put_url"].removeprefix("memory://put/")


async def _upload(client, storage, headers, data, kind="pdf", mime="application/pdf"):
    r = await _presign(client, headers, kind, mime, len(data))
    assert r.status_code == 200, r.text
    storage.objects[_key(r)] = data
    done = await client.post(f"{API}/uploads/{r.json()['asset_id']}/complete", headers=headers)
    return r, done


async def test_presign_returns_url_and_asset(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv)
    assert r.status_code == 200
    assert r.json()["asset_id"] and _key(r).startswith("pdf/") and _key(r).endswith(".pdf")


async def test_presign_rejects_mime_not_allowed_for_kind(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv, kind="pdf", mime="image/png")
    assert (r.status_code, r.json()["error"]["code"]) == (400, "INVALID_FILE_TYPE")


async def test_presign_rejects_declared_size_over_limit(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv, size=60 * 1024 * 1024)
    assert (r.status_code, r.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


async def test_complete_without_upload(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv)
    done = await client.post(f"{API}/uploads/{r.json()['asset_id']}/complete", headers=gv)
    assert (done.status_code, done.json()["error"]["code"]) == (400, "UPLOAD_MISSING")


async def test_complete_valid_pdf(client, storage):
    _, gv = await make_teacher(client)
    _, done = await _upload(client, storage, gv, PDF)
    assert done.status_code == 200
    assert done.json()["verified_at"] is not None and done.json()["size_bytes"] == len(PDF)


async def test_complete_rejects_renamed_executable(client, storage):
    _, gv = await make_teacher(client)
    r, done = await _upload(client, storage, gv, EXE)
    assert (done.status_code, done.json()["error"]["code"]) == (400, "INVALID_FILE_TYPE")
    assert _key(r) not in storage.objects
    again = await client.post(f"{API}/uploads/{r.json()['asset_id']}/complete", headers=gv)
    assert again.status_code == 404


async def test_complete_rejects_actual_size_over_limit(client, storage):
    _, sv = await make_student(client)
    big = b"a" * (20 * 1024 * 1024 + 1)
    r = await _presign(client, sv, kind="submission", mime="text/plain", size=100)
    storage.objects[_key(r)] = big
    done = await client.post(f"{API}/uploads/{r.json()['asset_id']}/complete", headers=sv)
    assert (done.status_code, done.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


async def test_other_user_cannot_complete(client, storage):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    r = await _presign(client, gv)
    storage.objects[_key(r)] = PDF
    done = await client.post(f"{API}/uploads/{r.json()['asset_id']}/complete", headers=sv)
    assert done.status_code == 404


async def test_attach_video_and_stream_url(client, storage):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    r, done = await _upload(client, storage, gv, MP4, kind="video", mime="video/mp4")
    assert done.status_code == 200
    patch = await client.patch(f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]},
                               headers=gv)
    assert patch.status_code == 200 and patch.json()["video_asset_id"] == r.json()["asset_id"]

    denied = await client.get(f"{API}/lessons/{lesson['id']}/video", headers=sv)
    assert denied.status_code == 403
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    ok = await client.get(f"{API}/lessons/{lesson['id']}/video", headers=sv)
    assert ok.status_code == 200 and ok.json()["url"] == f"memory://get/{_key(r)}"


async def test_attach_pdf_as_video_is_rejected(client, storage):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r, _ = await _upload(client, storage, gv, PDF)
    patch = await client.patch(f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]},
                               headers=gv)
    assert (patch.status_code, patch.json()["error"]["code"]) == (400, "INVALID_ASSET")
