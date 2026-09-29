"""Smoke test tuần 1: API, worker, MinIO, Postgres thật. Cần `docker compose up -d --build` trước.

Chạy từ thư mục backend/:  PYTHONUTF8=1 uv run python -m scripts.smoke_week1 [duong/dan/file.pdf]
Không truyền file thì tự sinh một PDF 2 trang có text.
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path

import httpx
import pymupdf

from app.core.db import SessionLocal, engine
from app.modules.auth.service import approve_teacher

API = "http://localhost:8000/api/v1"
SAMPLE = [
    "Chương 1. Tìm kiếm nhị phân\n\n"
    + "Tìm kiếm nhị phân chia đôi khoảng tìm kiếm trên mảng đã sắp xếp. " * 12,
    "Chương 2. Sắp xếp trộn\n\n" + "Sắp xếp trộn chia mảng làm hai nửa, sắp xếp từng nửa rồi trộn lại. " * 12,
]


def sample_pdf() -> bytes:
    doc = pymupdf.open()
    for body in SAMPLE:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 540, 770), body, fontsize=11, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data


async def _approve(email: str) -> None:
    async with SessionLocal() as db:
        await approve_teacher(db, email)
    await engine.dispose()  # asyncio.run đóng event loop: không giữ connection sang loop khác


def main(pdf_path: str | None) -> int:
    data = Path(pdf_path).read_bytes() if pdf_path else sample_pdf()
    email = f"smoke-{uuid.uuid4().hex[:6]}@example.com"
    h: dict[str, str] = {}
    with httpx.Client(base_url=API, timeout=30) as c:

        def post(url: str, **kw) -> dict:
            resp = c.post(url, headers=h, **kw)
            if resp.is_error:
                raise SystemExit(f"POST {url} → {resp.status_code}: {resp.text}")
            return resp.json()

        post(
            "/auth/register",
            json={"email": email, "password": "password123", "full_name": "Smoke GV", "role": "teacher"},
        )
        asyncio.run(_approve(email))
        h["Authorization"] = (
            "Bearer " + post("/auth/login", json={"email": email, "password": "password123"})["access_token"]
        )

        course = post("/courses", json={"title": "Khóa smoke test"})
        section = post(f"/courses/{course['id']}/sections", json={"title": "Chương 1"})
        lesson = post(f"/sections/{section['id']}/lessons", json={"title": "Bài 1"})

        pre = post("/uploads/presign", json={"kind": "pdf", "mime": "application/pdf", "size": len(data)})
        httpx.put(
            pre["put_url"], content=data, headers={"Content-Type": "application/pdf"}, timeout=120
        ).raise_for_status()  # PUT thẳng vào MinIO (key staging) như trình duyệt
        post(f"/uploads/{pre['asset_id']}/complete")

        created = post(f"/lessons/{lesson['id']}/sources", json={"asset_id": pre["asset_id"]})
        job_id, source_id = created["job_id"], created["source"]["id"]
        print("Đã gắn tài liệu, job:", job_id)

        deadline = time.time() + 180
        while True:
            job = c.get(f"/jobs/{job_id}", headers=h).json()
            if job["status"] in ("done", "failed") or time.time() > deadline:
                break
            time.sleep(2)
        print("Job:", job["status"], job.get("error_msg") or "")
        detail = c.get(f"/sources/{source_id}", headers=h).json()
        pages = c.get(f"/sources/{source_id}/pages", params={"size": 100}, headers=h).json()["items"]
        print(f"Source: {detail['status']} · {detail['page_count']} trang · {detail['chunk_count']} chunk")
        print("Cách trích từng trang:", [p["extraction_method"] for p in pages])
        ok = job["status"] == "done" and detail["status"] == "ready" and detail["chunk_count"] > 0
        print("SMOKE OK" if ok else "SMOKE FAILED")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
