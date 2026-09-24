import pytest

from rag.services import llm


def test_client_requires_api_key(settings):
    settings.OPENAI_API_KEY = ""
    with pytest.raises(llm.LLMUnavailable, match="OPENAI_API_KEY"):
        llm._client()


def test_empty_base_url_env_var_does_not_break_the_client(settings, monkeypatch):
    # docker-compose passes `OPENAI_BASE_URL=` through as an empty string.
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    settings.OPENAI_API_KEY = "test-key"
    assert str(llm._client().base_url).startswith("https://api.openai.com/v1")
