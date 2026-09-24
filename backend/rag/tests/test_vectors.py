import numpy as np
import pytest

from papers.models import Paper
from papers.services.ingestion import IngestionStats, ingest_records
from rag.models import PaperEmbedding
from rag.services.vectors import nearest, to_blob

pytestmark = pytest.mark.django_db


def test_to_blob_normalises_vectors():
    stored = np.frombuffer(to_blob([3.0, 4.0]), dtype=np.float32)
    assert stored.tolist() == pytest.approx([0.6, 0.8])


def store(paper, vector, model="m"):
    PaperEmbedding.objects.create(paper=paper, embedding=to_blob(vector), model=model, content_hash="x")


def test_nearest_orders_by_cosine_distance(make_record):
    ingest_records([make_record("2409.00001"), make_record("2409.00002"), make_record("2409.00003")],
                   IngestionStats())
    first, second, third = Paper.objects.order_by("arxiv_id")
    store(first, [1, 0, 0])
    store(second, [1, 1, 0])
    store(third, [0, 0, 1])

    results = nearest([1, 0.1, 0], model="m", top_k=2)

    assert [paper_id for paper_id, _ in results] == [first.pk, second.pk]
    assert results[0][1] == pytest.approx(1 - 1 / np.sqrt(1.01), abs=1e-5)


def test_nearest_ignores_other_models_and_empty_index(make_record):
    assert nearest([1, 0], model="m", top_k=3) == []
    ingest_records([make_record()], IngestionStats())
    store(Paper.objects.get(), [1, 0], model="old-model")
    assert nearest([1, 0], model="m", top_k=3) == []


def test_nearest_rejects_dimension_mismatch(make_record):
    ingest_records([make_record()], IngestionStats())
    store(Paper.objects.get(), [1, 0, 0])
    with pytest.raises(ValueError, match="dimensions"):
        nearest([1, 0], model="m", top_k=1)
