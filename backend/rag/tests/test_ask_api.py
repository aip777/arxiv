import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from papers.services.ingestion import IngestionStats, ingest_records
from rag.services.indexing import sync_index
from rag.services.llm import LLMUnavailable
from rag.services.qa import NO_MATCH_ANSWER, NOT_ANSWERABLE_ANSWER

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def indexed_papers(make_record, fake_llm):
    ingest_records(
        [
            make_record(
                "2409.00001",
                title="Graph neural networks for molecules",
                abstract="We apply graph neural networks to molecular property prediction.",
                authors=["Alice Smith"],
            ),
            make_record(
                "2409.00002",
                title="Reinforcement learning for robotics",
                abstract="Robots learn manipulation skills with reinforcement learning.",
                authors=["Bob Jones"],
            ),
            make_record(
                "2409.00003",
                title="Speech recognition with transformers",
                abstract="Transformers improve automatic speech recognition accuracy.",
                authors=["Carol White"],
            ),
        ],
        IngestionStats(),
    )
    sync_index()
    return fake_llm


def ask(client, **payload):
    return client.post(reverse("ask"), payload, format="json")


def test_answers_with_sources_from_the_closest_paper(client, indexed_papers):
    response = ask(client, question="Which graph neural networks predict molecular properties?")

    assert response.status_code == 200
    data = response.json()
    assert "2409.00001" in data["answer"]
    assert [source["arxiv_id"] for source in data["sources"]] == ["2409.00001"]
    source = data["sources"][0]
    assert source["title"] == "Graph neural networks for molecules"
    assert source["authors"] == ["Alice Smith"]
    assert source["primary_category"] == "cs.LG"
    assert source["published"] == "2024-09-01"
    assert source["url"].startswith("https://arxiv.org/abs/2409.00001")
    assert 0 < source["similarity"] <= 1


def test_context_sent_to_llm_contains_only_relevant_papers(client, indexed_papers):
    ask(client, question="reinforcement learning robots manipulation")

    _, user_prompt = indexed_papers.chat_calls[-1]
    assert "[2409.00002]" in user_prompt
    assert "Question: reinforcement learning robots manipulation" in user_prompt
    # Unrelated papers are beyond the distance cut-off and never reach the LLM.
    assert "[2409.00003]" not in user_prompt


def test_unrelated_question_gets_honest_no_match_without_llm_call(client, indexed_papers):
    response = ask(client, question="What is a good recipe for chocolate cake?")

    assert response.status_code == 200
    assert response.json() == {"answer": NO_MATCH_ANSWER, "sources": []}
    assert indexed_papers.chat_calls == []


def test_llm_saying_context_is_insufficient_returns_no_sources(client, indexed_papers):
    indexed_papers.next_response = {"answer": "", "cited_ids": [], "answerable": False}

    response = ask(client, question="What GPU did the graph neural networks molecules paper use?")

    assert response.status_code == 200
    assert response.json() == {"answer": NOT_ANSWERABLE_ANSWER, "sources": []}


def test_uncited_answer_falls_back_to_retrieved_papers(client, indexed_papers):
    indexed_papers.next_response = {
        "answer": "Graph networks work well.",
        "cited_ids": ["9999.99999"],
        "answerable": True,
    }

    response = ask(client, question="graph neural networks molecular property prediction")

    assert response.status_code == 200
    assert [s["arxiv_id"] for s in response.json()["sources"]] == ["2409.00001"]


def test_top_k_limits_retrieval(client, indexed_papers):
    ask(client, question="learning networks transformers robots molecules speech", top_k=1)
    _, user_prompt = indexed_papers.chat_calls[-1]
    assert user_prompt.count("\n---\n") == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "hi"},
        {"question": "x" * 1001},
        {"question": "valid question", "top_k": 0},
        {"question": "valid question", "top_k": 50},
    ],
)
def test_invalid_requests_return_400(client, indexed_papers, payload):
    response = client.post(reverse("ask"), payload, format="json")
    assert response.status_code == 400
    assert "detail" in response.json()


def test_empty_index_returns_503(client, fake_llm):
    response = ask(client, question="anything about transformers?")
    assert response.status_code == 503
    assert "ingest_arxiv" in response.json()["detail"]


def test_index_built_with_another_model_returns_503(client, indexed_papers, settings):
    settings.EMBEDDING_MODEL = "some-new-embedding-model"
    response = ask(client, question="graph neural networks molecular property prediction")
    assert response.status_code == 503
    assert "build_index" in response.json()["detail"]


def test_llm_failure_returns_503(client, indexed_papers, monkeypatch):
    def broken(*args, **kwargs):
        raise LLMUnavailable("provider down")

    monkeypatch.setattr("rag.services.llm.complete_json", broken)
    response = ask(client, question="graph neural networks molecular property prediction")

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_ask_is_rate_limited(client, indexed_papers, monkeypatch):
    # DRF reads throttle rates once at import time, so patch the class attribute directly.
    rates = {**ScopedRateThrottle.THROTTLE_RATES, "ask": "2/minute"}
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", rates)
    statuses = [ask(client, question="graph neural networks").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
