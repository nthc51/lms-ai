"""Body request của quiz/tutor không nhận trường lạ (gõ sai tên trường → 422 thay vì bị lặng lẽ bỏ qua)."""

import uuid

import pytest
from pydantic import ValidationError

from app.modules.quiz.schemas import (
    AnswerIn,
    DifficultyMix,
    FinalAnswer,
    QuestionReview,
    QuizCreate,
    QuizGenerateIn,
    QuizUpdate,
    SubmitIn,
)
from app.modules.tutor.schemas import AskIn, FeedbackIn, SessionCreate
from tests.helpers import API, make_published_course, make_published_quiz, make_teacher

VALID = [
    (QuizGenerateIn, {}),
    (DifficultyMix, {}),
    (QuestionReview, {"action": "approve"}),
    (QuizCreate, {"lesson_id": str(uuid.uuid4()), "title": "Quiz"}),
    (QuizUpdate, {}),
    (AnswerIn, {"selected_option_id": "A"}),
    (FinalAnswer, {"question_id": str(uuid.uuid4()), "selected_option_id": "A"}),
    (SubmitIn, {}),
    (SessionCreate, {"course_id": str(uuid.uuid4())}),
    (AskIn, {"content": "Câu hỏi"}),
    (FeedbackIn, {"value": 1}),
]


@pytest.mark.parametrize("schema, body", VALID, ids=[s.__name__ for s, _ in VALID])
def test_request_schemas_forbid_unknown_fields(schema, body):
    schema.model_validate(body)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        schema.model_validate({**body, "unknown_field": 1})


async def test_unknown_fields_are_rejected_by_the_api(client, db):
    gv, _, course, quiz, _ = await make_published_quiz(client, db)
    r = await client.patch(f"{API}/quizzes/{quiz['id']}", json={"titel": "Sai tên trường"}, headers=gv)
    assert r.status_code == 422
    body = {"course_id": course["id"], "scope": "course"}
    assert (await client.post(f"{API}/tutor/sessions", json=body, headers=gv)).status_code == 422


async def test_unknown_field_in_quiz_create_is_rejected(client):
    _, gv = await make_teacher(client, "gv3@x.com")
    _, _, lesson = await make_published_course(client, gv)
    body = {"lesson_id": lesson["id"], "title": "Quiz", "passing_score": 80}
    assert (await client.post(f"{API}/quizzes", json=body, headers=gv)).status_code == 422
