"""AI gợi ý chấm bài nộp theo rubric (B5, spec 5.6), chạy trong job nền grade_submission.

1. Đọc bài làm: phần gõ trực tiếp + chữ trích từ file đính kèm (PDF hoặc .txt).
2. Gọi AI với bài làm bọc trong <submission> (chống prompt injection: nội dung trong thẻ chỉ là dữ liệu).
3. Hậu kiểm: đủ và đúng các tiêu chí, ép điểm vào 0..max_points, kiểm câu trích có thật trong bài làm.
4. Chỉ ghi kết quả khi bài nộp vẫn đúng version đó và chưa được giảng viên chấm (nộp lại giữa chừng thì bỏ).
AI lỗi (sau một lần thử lại khi output sai) thì bài chuyển ai_failed và giảng viên chấm tay."""

import difflib
import logging
import re
import unicodedata
import uuid

import pymupdf
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.llm_client import LLMClient, LLMOutputError
from app.ai.prompts import load_prompt
from app.core.storage import Storage
from app.modules.assignment.models import Assignment, Submission, SubmissionStatus
from app.modules.assignment.service import teacher_link
from app.modules.courses.models import Course, Lesson, Section
from app.modules.inbox import service as inbox
from app.modules.inbox.hub import NotificationHub
from app.modules.inbox.models import NotificationKind
from app.modules.materials.models import Asset

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 30
MAX_SUBMISSION_CHARS = 40_000  # cắt bớt phần quá dài trước khi gửi AI (chi phí, giới hạn ngữ cảnh)
EVIDENCE_MATCH = 0.8  # tỉ lệ ký tự của câu trích phải khớp liền một đoạn trong bài làm
AI_ERROR = "AI không chấm được bài này, vui lòng chấm tay hoặc bấm AI chấm lại"


class GradingError(Exception):
    """Lỗi có thông báo tiếng Việt cho giảng viên (ghi vào submissions.ai_error)."""


class _CriterionDraft(BaseModel):
    key: str
    score: float
    justification: str
    evidence_quote: str


class GradeDraft(BaseModel):
    scores: list[_CriterionDraft]
    feedback: str


def pdf_text(data: bytes) -> str:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise GradingError("Không đọc được file PDF của bài nộp") from e
    with doc:
        if doc.page_count > MAX_PDF_PAGES:
            raise GradingError(f"File PDF quá dài (tối đa {MAX_PDF_PAGES} trang)")
        return "\n\n".join(page.get_text() for page in doc).strip()


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"[\"'“”‘’«»]", "", text)
    return " ".join(text.split())


def evidence_found(quote: str, submission: str) -> bool:
    """Câu trích có (gần như) nguyên văn trong bài làm: khớp liền ít nhất EVIDENCE_MATCH số ký tự của câu trích.
    Bỏ qua khác biệt chữ hoa/thường, khoảng trắng và dấu ngoặc kép."""
    q, s = _norm(quote), _norm(submission)
    if len(q) < 3:
        return False
    if q in s:
        return True
    match = difflib.SequenceMatcher(None, s, q, autojunk=False).find_longest_match(0, len(s), 0, len(q))
    return match.size >= EVIDENCE_MATCH * len(q)


def rubric_text(rubric: list[dict]) -> str:
    return "\n".join(
        f"- {r['key']}: {r['criterion']} (tối đa {r['max_points']} điểm)"
        + (f". Đạt khi: {r['description']}" if r.get("description") else "")
        for r in rubric
    )


def check_draft(draft: GradeDraft, rubric: list[dict], submission: str) -> dict:
    """Hậu kiểm output của AI. Thiếu / thừa / trùng tiêu chí → GradingError (coi như output sai, thử lại)."""
    keys = [r["key"] for r in rubric]
    got = [c.key for c in draft.scores]
    if sorted(got) != sorted(keys):
        raise GradingError(f"AI trả thiếu hoặc thừa tiêu chí: {', '.join(got) or '(trống)'}")
    limits = {r["key"]: r["max_points"] for r in rubric}
    scores = {}
    for c in draft.scores:
        score = round(min(max(c.score, 0.0), float(limits[c.key])), 2)
        quote = c.evidence_quote.strip()
        scores[c.key] = {
            "score": score,
            "justification": c.justification.strip(),
            "evidence_quote": quote,
            "evidence_found": bool(quote) and evidence_found(quote, submission),
        }
    return {
        "scores": {k: scores[k] for k in keys},
        "feedback": draft.feedback.strip(),
        "total": round(sum(s["score"] for s in scores.values()), 2),
    }


async def _read_submission(storage: Storage, text: str, asset: Asset | None) -> str:
    parts = [text.strip()] if text.strip() else []
    if asset is not None:
        data = await storage.read_all(asset.storage_key)
        if asset.mime == "application/pdf":
            parts.append(pdf_text(data))
        else:
            parts.append(data.decode("utf-8", errors="replace").strip())
    content = "\n\n".join(p for p in parts if p)
    if not content:
        raise GradingError("Bài nộp không có chữ nào để chấm (file có thể là ảnh scan)")
    return content[:MAX_SUBMISSION_CHARS]


async def ai_grade(
    llm: LLMClient, title: str, instructions: str, rubric: list[dict], content: str
) -> tuple[dict, str, str]:
    """Gọi AI chấm và hậu kiểm. Trả (kết quả, model, prompt_version). Dùng chung cho job và eval/grading.py."""
    prompt = load_prompt("assignment_grade").render(
        title=title,
        instructions=instructions,
        rubric=rubric_text(rubric),
        # học viên không đóng thẻ sớm được để chen chỉ thị vào phần ngoài thẻ
        submission=content.replace("</submission>", "< /submission>"),
    )
    last: Exception | None = None
    for _ in range(2):  # spec 5.7: output sai định dạng thì thử lại 1 lần
        try:
            # không cache: "AI chấm lại" phải gọi AI thật sự
            draft, result = await llm.generate_json(
                prompt, GradeDraft, op="assignment_grade", use_cache=False
            )
            return check_draft(draft, rubric, content), result.model, prompt.prompt_version
        except (LLMOutputError, GradingError) as e:
            last = e
            logger.warning("Output chấm bài không hợp lệ, thử lại: %s", e)
    raise GradingError(AI_ERROR) from last


async def grade_submission(
    submission_id: uuid.UUID,
    version: int,
    llm: LLMClient,
    storage: Storage,
    session_factory: async_sessionmaker,
    hub: NotificationHub | None = None,
) -> bool:
    """Chấm một version của bài nộp. Trả False nếu bỏ qua (đã nộp lại, đã được chấm, bị xóa).
    Lỗi thì ghi ai_failed rồi ném lại để job ghi failed."""
    async with session_factory() as db:
        row = (
            await db.execute(
                select(Submission, Assignment, Course)
                .join(Assignment, Assignment.id == Submission.assignment_id)
                .join(Lesson, Lesson.id == Assignment.lesson_id)
                .join(Section, Section.id == Lesson.section_id)
                .join(Course, Course.id == Section.course_id)
                .where(Submission.id == submission_id)
            )
        ).one_or_none()
        if row is None:
            return False
        sub, assignment, course = row
        if sub.version != version or sub.status != SubmissionStatus.submitted:
            return False
        asset = await db.get(Asset, sub.asset_id) if sub.asset_id else None
        text = sub.text_content
    # session đã đóng: không giữ kết nối DB trong lúc chờ AI

    try:
        content = await _read_submission(storage, text, asset)
        result, model, prompt_version = await ai_grade(
            llm, assignment.title, assignment.instructions, assignment.rubric, content
        )
    except Exception as e:
        message = str(e) if isinstance(e, GradingError) else AI_ERROR
        await _finish(session_factory, hub, submission_id, version, assignment, course, None, message)
        raise
    ai_result = {**result, "model": model, "prompt_version": prompt_version, "version": version}
    return await _finish(session_factory, hub, submission_id, version, assignment, course, ai_result, None)


async def _finish(
    session_factory: async_sessionmaker,
    hub: NotificationHub | None,
    submission_id: uuid.UUID,
    version: int,
    assignment: Assignment,
    course: Course,
    ai_result: dict | None,
    error: str | None,
) -> bool:
    """Ghi kết quả (hoặc lỗi) chỉ khi bài vẫn đúng version và chưa được chấm, rồi báo giảng viên của khóa."""
    async with session_factory() as db:
        values = (
            {"status": SubmissionStatus.ai_graded, "ai_result": ai_result, "ai_error": None}
            if ai_result is not None
            else {"status": SubmissionStatus.ai_failed, "ai_error": (error or AI_ERROR)[:500]}
        )
        written = await db.scalar(
            update(Submission)
            .where(
                Submission.id == submission_id,
                Submission.version == version,
                Submission.status == SubmissionStatus.submitted,
            )
            .values(**values)
            .returning(Submission.id)
        )
        if written is None:
            return False
        title = (
            f"Bài nộp mới có điểm AI gợi ý: {assignment.title}"
            if ai_result is not None
            else f"AI không chấm được một bài nộp: {assignment.title}"
        )
        notified = inbox.add(
            db,
            [course.teacher_id],
            NotificationKind.submission_ready,
            title,
            teacher_link(course, assignment, submission_id),
            "Xem gợi ý và xác nhận điểm" if ai_result is not None else (error or ""),
        )
        await db.commit()
    if hub is not None:
        await inbox.publish(hub, notified)
    return True
