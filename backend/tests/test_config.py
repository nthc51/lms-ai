import pytest
from pydantic import ValidationError

from app.ai.embedder import get_embedder
from app.ai.llm import get_llm_provider
from app.ai.vision import get_vision
from app.core.config import Settings


@pytest.mark.parametrize("field", ["llm_provider", "embed_provider", "vision_provider"])
def test_unknown_provider_is_rejected_at_boot(field):
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, **{field: "gemni"})


@pytest.mark.parametrize("field", ["LLM_PROVIDER", "EMBED_PROVIDER", "VISION_PROVIDER"])
def test_unknown_provider_from_env_is_rejected(field, monkeypatch):
    monkeypatch.setenv(field, "openai")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("field", ["llm_provider", "embed_provider", "vision_provider"])
def test_gemini_provider_requires_api_key(field):
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        Settings(_env_file=None, **{field: "gemini"}, gemini_api_key="  ")
    s = Settings(_env_file=None, **{field: "gemini"}, gemini_api_key="k")
    assert getattr(s, field) == "gemini"


def test_fake_providers_need_no_key():
    s = Settings(_env_file=None, gemini_api_key="")
    assert (s.llm_provider, s.embed_provider, s.vision_provider) == ("fake", "fake", "fake")


@pytest.mark.parametrize(
    "factory, field",
    [(get_llm_provider, "llm_provider"), (get_embedder, "embed_provider"), (get_vision, "vision_provider")],
)
def test_factories_raise_on_unknown_provider_instead_of_falling_back_to_fake(factory, field):
    # model_copy bỏ qua validate: mô phỏng Settings dựng bằng cách khác/giá trị lọt qua.
    s = Settings(_env_file=None).model_copy(update={field: "bogus"})
    with pytest.raises(ValueError, match="bogus"):
        factory(s)
