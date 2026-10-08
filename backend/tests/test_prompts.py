import string

import pytest

from app.ai.prompts import PROMPTS_DIR, load_prompt

EXPECTED_VARS = {
    "tutor_answer": {"course_title", "context", "question"},
    "tutor_rewrite": {"history", "question"},
    "quiz_generate": {"count", "difficulties", "heading", "source", "avoid", "feedback"},
    "quiz_self_check": {"source", "stem", "options"},
    # AI Studio
    "source_guide": {"document"},
    "studio_study_guide": {"scope", "context"},
    "studio_briefing": {"scope", "context"},
    "studio_faq": {"scope", "context"},
    "studio_timeline": {"scope", "context"},
    "studio_map": {"scope", "context"},
    "studio_flashcards": {"scope", "count", "context"},
    "tutor_followups": {"question", "answer", "sections"},
    "notes_synthesize": {"notes"},
    # benchmark
    "eval_judge": {"question", "gold", "context", "answer"},
    "eval_draft": {"count", "source"},
}


def _placeholders(body: str) -> set[str]:
    found = set()
    for m in string.Template.pattern.finditer(body):
        assert m.group("invalid") is None, f"Ký tự $ lạc chỗ ở vị trí {m.start()}"
        name = m.group("named") or m.group("braced")
        if name:
            found.add(name)
    return found


def test_every_prompt_file_is_versioned_and_uses_known_placeholders():
    assert {p.stem for p in PROMPTS_DIR.glob("*.md")} == set(EXPECTED_VARS)
    for name, variables in EXPECTED_VARS.items():
        template = load_prompt(name)
        assert template.version.startswith("v"), name
        assert _placeholders(template.body) == variables, name
        assert not template.body.startswith("---"), "front matter phải được tách khỏi thân prompt"


def test_render_substitutes_values_verbatim():
    template = load_prompt("tutor_rewrite")
    p = template.render(history="Học viên: giá $5 thì sao?", question="Còn cái kia?")
    assert "Học viên: giá $5 thì sao?" in p.text and "Còn cái kia?" in p.text
    assert p.prompt_version == f"tutor_rewrite@{template.version}" == template.prompt_version


def test_missing_variable_raises():
    with pytest.raises(KeyError):
        load_prompt("tutor_rewrite").render(history="")


def test_missing_front_matter_is_rejected(tmp_path, monkeypatch):
    from app.ai import prompts

    (tmp_path / "bad.md").write_text("Không có version", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    load_prompt.cache_clear()
    try:
        with pytest.raises(ValueError, match="version"):
            prompts.load_prompt("bad")
    finally:
        load_prompt.cache_clear()


def test_front_matter_with_crlf_line_endings_is_accepted(tmp_path, monkeypatch):
    from app.ai import prompts

    crlf = "---\r\nversion: v3\r\n---\r\nXin chào $name\r\n"
    m = prompts._FRONT_MATTER.match(crlf)  # regex chấp nhận CRLF kể cả khi nội dung không qua text mode
    assert m is not None and m.group(1) == "v3" and crlf[m.end() :] == "Xin chào $name\r\n"
    (tmp_path / "crlf.md").write_bytes(crlf.encode("utf-8"))
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    load_prompt.cache_clear()
    try:
        template = prompts.load_prompt("crlf")
        assert template.version == "v3"
        assert template.render(name="bạn").text.strip() == "Xin chào bạn"
    finally:
        load_prompt.cache_clear()
