import hashlib
import math
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from papers.services.parser import PaperRecord
from rag.models import EMBEDDING_DIMENSIONS

FIXTURES = Path(__file__).parent / "papers" / "tests" / "fixtures"
STOPWORDS = {"the", "and", "for", "with", "that", "this", "are", "how", "what", "which", "from", "does", "use"}


def fake_embedding(text: str) -> list[float]:
    """
    Deterministic bag-of-words vector: texts sharing words end up close in
    cosine space, unrelated texts end up orthogonal. Good enough to test retrieval.
    """
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in re.findall(r"[a-z]{3,}", text.lower()):
        if word in STOPWORDS:
            continue
        slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS
        vector[slot] += 1.0
    if not any(vector):
        vector[0] = 1.0  # avoid a zero vector, which has no cosine distance
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector]


class FakeLLM:
    """Stands in for the OpenAI calls; records what it was asked."""

    def __init__(self):
        self.embed_calls = []
        self.chat_calls = []
        self.next_response = None

    def embed_texts(self, texts):
        self.embed_calls.append(list(texts))
        return [fake_embedding(text) for text in texts]

    def complete_json(self, system_prompt, user_prompt):
        self.chat_calls.append((system_prompt, user_prompt))
        if self.next_response is not None:
            return self.next_response
        cited = re.findall(r"^\[([^\]]+)\]", user_prompt, flags=re.MULTILINE)
        return {"answer": f"Based on [{cited[0]}], here is the answer.", "cited_ids": cited[:1], "answerable": True}


@pytest.fixture
def fake_llm(monkeypatch, settings):
    settings.OPENAI_API_KEY = "test-key"
    fake = FakeLLM()
    monkeypatch.setattr("rag.services.llm.embed_texts", fake.embed_texts)
    monkeypatch.setattr("rag.services.llm.complete_json", fake.complete_json)
    return fake


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    from django.core.cache import cache
    cache.clear()


@pytest.fixture
def atom_feed():
    return (FIXTURES / "arxiv_feed.xml").read_text()


@pytest.fixture
def make_record():
    def _make(arxiv_id="2409.00001", **overrides):
        values = {
            "arxiv_id": arxiv_id,
            "version": 1,
            "title": f"Paper {arxiv_id}",
            "abstract": "We study graph neural networks for molecular property prediction.",
            "authors": ["Alice Smith", "Bob Jones"],
            "primary_category": "cs.LG",
            "categories": ["cs.LG", "cs.AI"],
            "published": datetime(2024, 9, 1, 12, 0, tzinfo=UTC),
            "updated": datetime(2024, 9, 1, 12, 0, tzinfo=UTC),
            "doi": None,
            "journal_ref": None,
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}v1",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}v1",
        }
        values.update(overrides)
        return PaperRecord(**values)
    return _make
