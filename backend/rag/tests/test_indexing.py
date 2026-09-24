import pytest

from papers.models import Paper
from papers.services.ingestion import IngestionStats, ingest_records, upsert_paper
from rag.models import PaperEmbedding
from rag.services.indexing import stale_papers, sync_index
from rag.services.llm import LLMUnavailable

pytestmark = pytest.mark.django_db


def test_sync_embeds_new_papers_in_batches(make_record, fake_llm):
    ingest_records([make_record(f"2409.0000{i}") for i in range(5)], IngestionStats())

    assert sync_index(batch_size=2) == 5

    assert PaperEmbedding.objects.count() == 5
    assert [len(batch) for batch in fake_llm.embed_calls] == [2, 2, 1]
    embedding = PaperEmbedding.objects.select_related("paper").first()
    assert embedding.content_hash == embedding.paper.content_hash
    assert embedding.model == "text-embedding-3-small"


def test_sync_is_a_no_op_when_up_to_date(make_record, fake_llm):
    ingest_records([make_record()], IngestionStats())
    sync_index()
    fake_llm.embed_calls.clear()

    assert sync_index() == 0
    assert fake_llm.embed_calls == []


def test_changed_abstract_is_re_embedded(make_record, fake_llm):
    upsert_paper(make_record(abstract="Original abstract about robots."))
    sync_index()

    upsert_paper(make_record(abstract="A completely new abstract about proteins."))
    assert stale_papers().count() == 1
    assert sync_index() == 1

    embedding = PaperEmbedding.objects.get()
    assert embedding.content_hash == Paper.objects.get().content_hash
    assert "proteins" in fake_llm.embed_calls[-1][0]


def test_metadata_only_change_does_not_re_embed(make_record, fake_llm):
    upsert_paper(make_record())
    sync_index()

    upsert_paper(make_record(doi="10.1/new", journal_ref="Some Journal 2024"))
    assert stale_papers().count() == 0


def test_changing_embedding_model_marks_everything_stale(make_record, fake_llm, settings):
    ingest_records([make_record("2409.00001"), make_record("2409.00002")], IngestionStats())
    sync_index()

    settings.EMBEDDING_MODEL = "another-embedding-model"
    assert stale_papers().count() == 2


def test_sync_without_api_key_raises(make_record, settings):
    settings.OPENAI_API_KEY = ""
    upsert_paper(make_record())
    with pytest.raises(LLMUnavailable):
        sync_index()
