from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from basebox.models import ScheduledTaskLog
from papers.models import Author, Category, Paper, PaperAuthor
from papers.services.arxiv_client import ArxivClientError
from papers.services.ingestion import (
    CREATED,
    UNCHANGED,
    UPDATED,
    IngestionStats,
    ingest_from_arxiv,
    ingest_records,
    reset_dataset,
    upsert_paper,
)
from papers.services.parser import FeedPage
from rag.models import PaperEmbedding
from rag.services.indexing import sync_index

pytestmark = pytest.mark.django_db


class FakeArxivClient:
    """Yields pre-built pages, optionally failing after them."""

    def __init__(self, pages, error=None):
        self.pages = pages
        self.error = error
        self.pages_served = 0

    def iter_pages(self, categories, max_results, page_size):
        for records in self.pages:
            self.pages_served += 1
            yield FeedPage(total_results=100, records=records, entry_count=len(records))
        if self.error:
            raise self.error


def test_upsert_creates_paper_with_authors_and_categories(make_record):
    record = make_record(authors=["Alice Smith", "Bob Jones"], categories=["cs.LG", "cs.AI"])

    assert upsert_paper(record) == CREATED

    paper = Paper.objects.get(arxiv_id=record.arxiv_id)
    assert paper.primary_category.code == "cs.LG"
    assert sorted(c.code for c in paper.categories.all()) == ["cs.AI", "cs.LG"]
    authorships = PaperAuthor.objects.filter(paper=paper).order_by("position")
    assert [(a.position, a.author.name) for a in authorships] == [(0, "Alice Smith"), (1, "Bob Jones")]


def test_rerunning_the_same_records_does_not_duplicate(make_record):
    records = [make_record("2409.00001"), make_record("2409.00002")]
    stats = IngestionStats()

    ingest_records(records, stats)
    ingest_records(records, stats)

    assert Paper.objects.count() == 2
    assert Author.objects.count() == 2
    assert Category.objects.count() == 2
    assert PaperAuthor.objects.count() == 4
    assert (stats.created, stats.updated, stats.unchanged) == (2, 0, 2)


def test_changed_papers_are_updated_in_place(make_record):
    upsert_paper(make_record())
    revised = make_record(
        version=2,
        title="A revised title",
        authors=["Bob Jones", "Carol White"],
        categories=["cs.LG", "stat.ML"],
        doi="10.1/abc",
        updated=make_record().updated + timedelta(days=3),
    )

    assert upsert_paper(revised) == UPDATED

    paper = Paper.objects.get()
    assert paper.version == 2
    assert paper.title == "A revised title"
    assert paper.doi == "10.1/abc"
    assert paper.content_hash == revised.content_hash
    assert sorted(c.code for c in paper.categories.all()) == ["cs.LG", "stat.ML"]
    assert [pa.author.name for pa in paper.authorships.order_by("position")] == ["Bob Jones", "Carol White"]


def test_author_order_change_counts_as_update(make_record):
    upsert_paper(make_record(authors=["Alice Smith", "Bob Jones"]))
    assert upsert_paper(make_record(authors=["Bob Jones", "Alice Smith"])) == UPDATED
    assert upsert_paper(make_record(authors=["Bob Jones", "Alice Smith"])) == UNCHANGED


def test_one_bad_record_does_not_stop_the_batch(make_record, monkeypatch):
    good, bad = make_record("2409.00001"), make_record("2409.00002")
    original = upsert_paper

    def flaky_upsert(record):
        if record.arxiv_id == bad.arxiv_id:
            raise RuntimeError("database hiccup")
        return original(record)

    monkeypatch.setattr("papers.services.ingestion.upsert_paper", flaky_upsert)
    stats = IngestionStats()
    ingest_records([bad, good], stats)

    assert stats.failed == 1
    assert stats.created == 1
    assert Paper.objects.filter(arxiv_id=good.arxiv_id).exists()


def test_ingest_from_arxiv_records_a_successful_run(make_record):
    client = FakeArxivClient([[make_record("2409.00001"), make_record("2409.00002")], [make_record("2409.00003")]])

    stats = ingest_from_arxiv(["cs.LG"], max_results=10, page_size=2, client=client)

    assert stats.fetched == 3
    assert stats.created == 3
    log = ScheduledTaskLog.objects.get(name="arxiv_ingestion")
    assert log.status == "success"
    assert log.json_meta["stats"]["created"] == 3


def test_incremental_run_stops_at_first_known_page(make_record):
    known_page = [make_record("2409.00001"), make_record("2409.00002")]
    ingest_records(known_page, IngestionStats())

    client = FakeArxivClient([[make_record("2409.00003")], known_page, [make_record("2409.00004")]])
    stats = ingest_from_arxiv(["cs.LG"], max_results=10, page_size=2, incremental=True, client=client)

    assert client.pages_served == 2
    assert stats.created == 1
    assert not Paper.objects.filter(arxiv_id="2409.00004").exists()


def test_failed_run_keeps_partial_progress_and_is_logged(make_record):
    client = FakeArxivClient([[make_record("2409.00001")]], error=ArxivClientError("HTTP 503"))

    with pytest.raises(ArxivClientError):
        ingest_from_arxiv(["cs.LG"], max_results=10, page_size=1, client=client)

    assert Paper.objects.count() == 1
    log = ScheduledTaskLog.objects.get(name="arxiv_ingestion")
    assert log.status == "failed"
    assert "HTTP 503" in log.message


def test_reset_dataset_removes_everything(make_record, fake_llm):
    ingest_records([make_record("2409.00001"), make_record("2409.00002")], IngestionStats())
    sync_index()
    assert PaperEmbedding.objects.count() == 2

    counts = reset_dataset()

    assert counts == {"embeddings": 2, "papers": 2, "authors": 2, "categories": 2}
    for model in (Paper, Author, Category, PaperAuthor, PaperEmbedding):
        assert not model.objects.exists()


def test_ingest_command_stores_papers_and_builds_index(make_record, fake_llm, monkeypatch):
    client = FakeArxivClient([[make_record("2409.00001"), make_record("2409.00002")]])
    monkeypatch.setattr("papers.services.ingestion.ArxivClient", lambda: client)

    call_command("ingest_arxiv", "--categories", "cs.LG", "--max-results", "2")

    assert Paper.objects.count() == 2
    assert PaperEmbedding.objects.count() == 2


def test_ingest_command_without_api_key_still_stores_papers(make_record, settings, monkeypatch):
    settings.OPENAI_API_KEY = ""
    client = FakeArxivClient([[make_record("2409.00001")]])
    monkeypatch.setattr("papers.services.ingestion.ArxivClient", lambda: client)

    call_command("ingest_arxiv", "--max-results", "1")

    assert Paper.objects.count() == 1
    assert PaperEmbedding.objects.count() == 0


def test_ingest_command_reports_arxiv_failure(monkeypatch):
    client = FakeArxivClient([], error=ArxivClientError("HTTP 503"))
    monkeypatch.setattr("papers.services.ingestion.ArxivClient", lambda: client)

    with pytest.raises(CommandError, match="re-run to resume"):
        call_command("ingest_arxiv", "--skip-embeddings")


def test_ingest_command_validates_arguments():
    with pytest.raises(CommandError):
        call_command("ingest_arxiv", "--max-results", "0")
    with pytest.raises(CommandError):
        call_command("ingest_arxiv", "--page-size", "5000")


def test_reset_command_requires_confirmation(make_record, monkeypatch):
    ingest_records([make_record()], IngestionStats())

    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(CommandError):
        call_command("reset_dataset")
    assert Paper.objects.count() == 1

    call_command("reset_dataset", "--yes")
    assert Paper.objects.count() == 0
