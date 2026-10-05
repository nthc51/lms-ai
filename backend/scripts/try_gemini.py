"""Thử AI thật trên một file PDF của bạn: xử lý tài liệu, hỏi AI Tutor, sinh câu hỏi (2 lần).

Khác smoke test ở chỗ IN RA NỘI DUNG để bạn tự đánh giá chất lượng: câu trả lời hiện dần theo
thời gian thực, trích dẫn kèm số trang, các câu hỏi sinh ra kèm đáp án và giải thích.

Chuẩn bị: `docker compose up -d --build` với backend/.env đã đặt provider = gemini và GEMINI_API_KEY.
Chạy từ thư mục backend/ (PowerShell):
    $env:PYTHONUTF8=1; uv run python -m scripts.try_gemini D:\\tai-lieu\\giao-trinh.pdf "Câu hỏi 1?" "Câu hỏi 2?"
Không truyền câu hỏi thì dùng 3 câu mặc định (2 câu về tài liệu nói chung + 1 câu ngoài lề để thử từ chối).
Tùy chọn: --count 5 (số câu hỏi sinh mỗi lần, mặc định 5).
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from scripts.smoke_week1 import API, _approve

DEFAULT_QUESTIONS = [
    "Tóm tắt ý chính của tài liệu này trong 3 câu.",
    "Khái niệm quan trọng nhất trong tài liệu là gì? Giải thích kèm ví dụ.",
    "Thủ đô của nước Pháp là gì?",  # ngoài tài liệu: mong đợi AI từ chối
]


def iter_sse(resp: httpx.Response):
    """Đọc SSE dần dần (in token ngay khi tới, không đợi hết stream)."""
    buf = ""
    for chunk in resp.iter_text():
        buf += chunk.replace("\r\n", "\n")
        while "\n\n" in buf:
            block, buf = buf.split("\n\n", 1)
            event, data = "message", []
            for line in block.split("\n"):
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].lstrip())
            if data:
                yield event, json.loads("\n".join(data))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("questions", nargs="*")
    ap.add_argument("--count", type=int, default=5)
    args = ap.parse_args()
    data = args.pdf.read_bytes()
    questions = args.questions or DEFAULT_QUESTIONS
    tag = uuid.uuid4().hex[:6]
    gv_email, sv_email = f"try-gv-{tag}@example.com", f"try-sv-{tag}@example.com"
    problems: list[str] = []

    with httpx.Client(base_url=API, timeout=120) as c:

        def call(method: str, url: str, headers: dict, **kw):
            resp = c.request(method, url, headers=headers, **kw)
            if resp.is_error:
                raise SystemExit(f"{method} {url} → {resp.status_code}: {resp.text}")
            return resp.json() if resp.content else None

        def account(email: str, role: str) -> dict[str, str]:
            body = {"email": email, "password": "password123", "full_name": f"Thử {role}", "role": role}
            call("POST", "/auth/register", {}, json=body)
            if role == "teacher":
                asyncio.run(_approve(email))
            login = {"email": email, "password": "password123"}
            return {"Authorization": f"Bearer {call('POST', '/auth/login', {}, json=login)['access_token']}"}

        def wait_job(job_id: str, headers: dict, label: str) -> dict:
            start, deadline = time.time(), time.time() + 900
            while True:
                job = call("GET", f"/jobs/{job_id}", headers)
                if job["status"] in ("done", "failed") or time.time() > deadline:
                    print(
                        f"  {label}: {job['status']} sau {time.time() - start:.0f}s {job.get('error_msg') or ''}"
                    )
                    return job
                time.sleep(3)

        print("== 1. Xử lý tài liệu ==")
        gv = account(gv_email, "teacher")
        course = call("POST", "/courses", gv, json={"title": f"Thử Gemini {tag}"})
        section = call("POST", f"/courses/{course['id']}/sections", gv, json={"title": "Chương 1"})
        lesson = call("POST", f"/sections/{section['id']}/lessons", gv, json={"title": args.pdf.stem[:150]})
        pre = call(
            "POST", "/uploads/presign", gv, json={"kind": "pdf", "mime": "application/pdf", "size": len(data)}
        )
        httpx.put(
            pre["put_url"], content=data, headers={"Content-Type": "application/pdf"}, timeout=300
        ).raise_for_status()
        call("POST", f"/uploads/{pre['asset_id']}/complete", gv)
        created = call("POST", f"/lessons/{lesson['id']}/sources", gv, json={"asset_id": pre["asset_id"]})
        if wait_job(created["job_id"], gv, "ingest_pdf")["status"] != "done":
            problems.append("xử lý PDF thất bại")
        src = call("GET", f"/sources/{created['source']['id']}", gv)
        print(
            f"  {src['page_count']} trang · {src['chunk_count']} đoạn · {src['vision_pages']} trang đọc bằng vision"
            + (f" · cảnh báo: {src['warning']}" if src.get("warning") else "")
        )
        first = call("GET", f"/sources/{src['id']}/pages", gv, params={"size": 1})["items"]
        if first:
            print("  Trang 1 trích được (300 ký tự đầu):", first[0]["markdown"][:300].replace("\n", " "))
        call("POST", f"/courses/{course['id']}/publish", gv)

        print("\n== 2. AI Tutor ==")
        sv = account(sv_email, "student")
        call("POST", f"/courses/{course['id']}/enroll", sv)
        session = call(
            "POST", "/tutor/sessions", sv, json={"course_id": course["id"], "lesson_id": lesson["id"]}
        )
        for q in questions:
            print(f"\n» Hỏi: {q}")
            start, ttft, last = time.time(), None, None
            with c.stream(
                "POST", f"/tutor/sessions/{session['id']}/messages", headers=sv, json={"content": q}
            ) as r:
                if r.is_error:
                    r.read()
                    raise SystemExit(f"Tutor → {r.status_code}: {r.text}")
                for event, d in iter_sse(r):
                    last = (event, d)
                    if event == "sources":
                        pages = [s.get("page_no") for s in d["sources"]]
                        print(f"  [nguồn tìm được: {len(pages)} đoạn, trang {pages}]")
                    elif event == "token":
                        ttft = ttft or time.time() - start
                        print(d["text"], end="", flush=True)
                    elif event == "error":
                        print(f"\n  !! error: {d}")
            total = time.time() - start
            print(f"\n  [token đầu sau {ttft or 0:.1f}s · tổng {total:.1f}s]")
            if last and last[0] == "done":
                cites = [f"[{x['n']}] trang {x['page_no']}" for x in last[1]["citations"]]
                print(f"  [từ chối: {last[1]['refused']} · trích dẫn: {', '.join(cites) or 'không có'}]")
            else:
                problems.append(f"Tutor không trả 'done' cho câu: {q}")

        print("\n== 3. Sinh câu hỏi (2 lần trên cùng bài) ==")
        stems: list[str] = []
        for round_no in (1, 2):
            gen = call("POST", f"/lessons/{lesson['id']}/questions/generate", gv, json={"count": args.count})
            if wait_job(gen["job_id"], gv, f"quiz_gen lần {round_no}")["status"] != "done":
                problems.append(f"sinh câu hỏi lần {round_no} thất bại")
            items = call(
                "GET",
                f"/lessons/{lesson['id']}/questions",
                gv,
                params={"review_status": "pending", "size": 100},
            )["items"]
            new = [x for x in items if x["stem"] not in stems]
            for i, x in enumerate(new, 1):
                print(f"\n  Câu {round_no}.{i} [{x['difficulty']}] {x['stem']}")
                for o in x["options"]:
                    mark = "✓" if o["id"] == x["correct_option_id"] else " "
                    print(f"    {mark} {o['id']}. {o['text']}")
                print(f"    Giải thích: {x['explanation']}")
            stems += [x["stem"] for x in new]
        print(f"\n  Tổng {len(stems)} câu khác nhau sau 2 lần sinh.")

    print("\n" + ("TRY OK" if not problems else "CÓ VẤN ĐỀ: " + "; ".join(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
