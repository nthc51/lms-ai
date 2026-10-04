"""Smoke test tuần 2 (A5–A8) trên docker stack thật với provider giả (LLM_PROVIDER=fake, EMBED_PROVIDER=fake).
Cần `docker compose up -d --build` trước (api và worker đều chạy provider giả: LLM_PROVIDER mặc định là fake).

Chạy từ thư mục backend/:  PYTHONUTF8=1 uv run python -m scripts.smoke_week2
Luồng: giảng viên tạo khóa, gắn PDF → học viên đăng ký, hỏi Tutor qua SSE → giảng viên sinh câu hỏi, duyệt,
tạo quiz, xuất bản → học viên làm quiz, nộp, xem kết quả → giảng viên xem analytics."""

import asyncio
import json
import sys
import time
import uuid

import httpx

from scripts.smoke_week1 import API, _approve, sample_pdf


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def main() -> int:
    tag = uuid.uuid4().hex[:6]
    gv_email, sv_email = f"smoke-gv-{tag}@example.com", f"smoke-sv-{tag}@example.com"
    with httpx.Client(base_url=API, timeout=60) as c:

        def call(method: str, url: str, headers: dict, **kw):
            resp = c.request(method, url, headers=headers, **kw)
            if resp.is_error:
                raise SystemExit(f"{method} {url} → {resp.status_code}: {resp.text}")
            return resp.json() if resp.content else None

        def login(email: str) -> dict[str, str]:
            token = call("POST", "/auth/login", {}, json={"email": email, "password": "password123"})[
                "access_token"
            ]
            return {"Authorization": f"Bearer {token}"}

        def register(email: str, role: str) -> None:
            body = {"email": email, "password": "password123", "full_name": f"Smoke {role}", "role": role}
            call("POST", "/auth/register", {}, json=body)

        def wait_job(job_id: str, headers: dict) -> dict:
            deadline = time.time() + 300
            while True:
                job = call("GET", f"/jobs/{job_id}", headers)
                if job["status"] in ("done", "failed") or time.time() > deadline:
                    return job
                time.sleep(2)

        # giảng viên: khóa + tài liệu
        register(gv_email, "teacher")
        asyncio.run(_approve(gv_email))
        gv = login(gv_email)
        course = call("POST", "/courses", gv, json={"title": "Khóa smoke tuần 2"})
        section = call("POST", f"/courses/{course['id']}/sections", gv, json={"title": "Chương 1"})
        lesson = call("POST", f"/sections/{section['id']}/lessons", gv, json={"title": "Bài 1"})
        data = sample_pdf()
        pre = call(
            "POST", "/uploads/presign", gv, json={"kind": "pdf", "mime": "application/pdf", "size": len(data)}
        )
        httpx.put(
            pre["put_url"], content=data, headers={"Content-Type": "application/pdf"}, timeout=120
        ).raise_for_status()
        call("POST", f"/uploads/{pre['asset_id']}/complete", gv)
        created = call("POST", f"/lessons/{lesson['id']}/sources", gv, json={"asset_id": pre["asset_id"]})
        ingest = wait_job(created["job_id"], gv)
        print("Xử lý tài liệu:", ingest["status"], ingest.get("error_msg") or "")
        call("POST", f"/courses/{course['id']}/publish", gv)

        # học viên: hỏi Tutor qua SSE
        register(sv_email, "student")
        sv = login(sv_email)
        call("POST", f"/courses/{course['id']}/enroll", sv)
        avail = call("GET", "/tutor/availability", sv, params={"course_id": course["id"]})
        print("Tutor khả dụng:", avail)
        session = call(
            "POST", "/tutor/sessions", sv, json={"course_id": course["id"], "lesson_id": lesson["id"]}
        )
        with c.stream(
            "POST",
            f"/tutor/sessions/{session['id']}/messages",
            headers=sv,
            json={"content": "Tìm kiếm nhị phân là gì?"},
        ) as r:
            r.raise_for_status()
            events = parse_sse("".join(r.iter_text()))
        names = [e for e, _ in events]
        done = events[-1][1] if names and names[-1] == "done" else {}
        cited = [x["n"] for x in done.get("citations", [])]
        print(f"SSE: {names[0]} → {names.count('token')} token → {names[-1]} · trích dẫn {cited}")

        # giảng viên: sinh câu hỏi, duyệt, tạo quiz
        gen = call("POST", f"/lessons/{lesson['id']}/questions/generate", gv, json={"count": 4})
        qjob = wait_job(gen["job_id"], gv)
        params = {"review_status": "pending"}
        pending = call("GET", f"/lessons/{lesson['id']}/questions", gv, params=params)["items"]
        print("Sinh câu hỏi:", qjob["status"], qjob.get("error_msg") or "", f"· {len(pending)} câu chờ duyệt")
        for q in pending:
            call("PATCH", f"/questions/{q['id']}", gv, json={"action": "approve"})
        body = {"lesson_id": lesson["id"], "title": "Quiz smoke", "question_ids": [q["id"] for q in pending]}
        quiz = call("POST", "/quizzes", gv, json=body)
        call("POST", f"/quizzes/{quiz['id']}/publish", gv)
        listed = call("GET", "/quizzes", gv, params={"lesson_id": lesson["id"]})["items"]

        # học viên: làm quiz
        attempt = call("POST", f"/quizzes/{quiz['id']}/attempts", sv)
        leaked = "correct_option_id" in json.dumps(attempt)
        for q in attempt["questions"]:
            answer = {"selected_option_id": q["options"][0]["id"]}
            call("PUT", f"/attempts/{attempt['id']}/answers/{q['id']}", sv, json=answer)
        result = call("POST", f"/attempts/{attempt['id']}/submit", sv, json={})
        again = call("GET", f"/attempts/{attempt['id']}/result", sv)
        print(
            f"Quiz: {result['correct_count']}/{result['total']} · điểm {result['score']} · lộ đáp án: {leaked}"
        )

        stats = call("GET", f"/courses/{course['id']}/analytics", gv)
        print("Analytics:", {k: stats[k] for k in ("enrollments", "completed_enrollments", "tutor")})

        ok = (
            ingest["status"] == "done"
            and avail["available"]
            and names[:1] == ["sources"]
            and bool(done)
            and qjob["status"] == "done"
            and len(pending) > 0
            and len(listed) == 1
            and not leaked
            and result["status"] == "completed"
            and again["score"] == result["score"]
            and all("correct_option_id" in x and x["explanation"] for x in result["questions"])
            and stats["tutor"]["questions"] == 1
            and stats["quizzes"][0]["attempts"] == 1
        )
        print("SMOKE OK" if ok else "SMOKE FAILED")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
