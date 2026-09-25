"""
Thin wrapper around the OpenAI API for embeddings and chat completions.

Everything else in the RAG pipeline goes through these two functions, which
keeps the provider in one place and makes the pipeline easy to fake in tests.
`OPENAI_BASE_URL` can point at any OpenAI-compatible server.
"""

import json
import logging

import openai
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """The model provider is not configured or did not return a usable response."""


def _client() -> openai.OpenAI:
    if not settings.OPENAI_API_KEY:
        raise LLMUnavailable("OPENAI_API_KEY is not configured.")
    return openai.OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.LLM_TIMEOUT,
        max_retries=2,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    client = _client()
    try:
        response = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    except openai.OpenAIError as exc:
        logger.error("Embedding request failed: %s", exc)
        raise LLMUnavailable(f"Embedding request failed: {exc}") from exc

    vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
    if len(vectors) != len(texts):
        raise LLMUnavailable(
            f"Embedding model {settings.EMBEDDING_MODEL!r} returned {len(vectors)} vectors for {len(texts)} texts."
        )
    return vectors


def complete_json(system_prompt: str, user_prompt: str) -> dict:
    """Run a chat completion that must return a JSON object."""
    client = _client()
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
    except openai.OpenAIError as exc:
        logger.error("Chat completion failed: %s", exc)
        raise LLMUnavailable(f"Chat completion failed: {exc}") from exc

    content = response.choices[0].message.content or ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned invalid JSON: %.200s", content)
        raise LLMUnavailable("The language model returned an invalid response.") from exc
    if not isinstance(data, dict):
        raise LLMUnavailable("The language model returned an invalid response.")
    return data
