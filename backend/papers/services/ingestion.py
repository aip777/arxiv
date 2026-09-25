"""
Load parsed arXiv records into the database.

Every paper is upserted in its own transaction keyed on `arxiv_id`, so a run can
be interrupted or repeated at any point without creating duplicates.
"""

import logging
from dataclasses import asdict, dataclass

from django.db import transaction

from basebox.models import ScheduledTaskLog
from papers.models import Author, Category, Paper, PaperAuthor
from papers.services.arxiv_client import ArxivClient
from papers.services.parser import PaperRecord
from rag.models import PaperEmbedding

logger = logging.getLogger(__name__)

CREATED = "created"
UPDATED = "updated"
UNCHANGED = "unchanged"

SCALAR_FIELDS = [
    "version",
    "title",
    "abstract",
    "published",
    "updated",
    "doi",
    "journal_ref",
    "comment",
    "abs_url",
    "pdf_url",
    "content_hash",
]


@dataclass
class IngestionStats:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0

    def as_dict(self):
        return asdict(self)

    def __str__(self):
        return ", ".join(f"{key}={value}" for key, value in self.as_dict().items())


def _get_or_create_all(model, field: str, values: list[str]) -> dict:
    """Return {value: row} for every value, inserting the ones that don't exist yet."""
    model.objects.bulk_create([model(**{field: value}) for value in values], ignore_conflicts=True)
    return {getattr(row, field): row for row in model.objects.filter(**{f"{field}__in": values})}


def _has_changed(paper: Paper, record: PaperRecord) -> bool:
    if paper.primary_category.code != record.primary_category:
        return True
    if any(getattr(paper, name) != getattr(record, name) for name in SCALAR_FIELDS):
        return True
    current_categories = {c.code for c in paper.categories.all()}
    if current_categories != set(record.categories):
        return True
    current_authors = [pa.author.name for pa in paper.authorships.select_related("author").order_by("position")]
    return current_authors != record.authors


def upsert_paper(record: PaperRecord) -> str:
    """Insert or update one paper with its authors and categories. Returns the outcome."""
    with transaction.atomic():
        paper = Paper.objects.select_related("primary_category").filter(arxiv_id=record.arxiv_id).first()
        if paper is not None and not _has_changed(paper, record):
            return UNCHANGED

        categories = _get_or_create_all(Category, "code", record.categories)
        values = {name: getattr(record, name) for name in SCALAR_FIELDS}
        values["primary_category"] = categories[record.primary_category]

        if paper is None:
            paper = Paper.objects.create(arxiv_id=record.arxiv_id, **values)
            outcome = CREATED
        else:
            for name, value in values.items():
                setattr(paper, name, value)
            paper.save()
            outcome = UPDATED

        paper.categories.set(categories.values())

        authors = _get_or_create_all(Author, "name", record.authors)
        PaperAuthor.objects.filter(paper=paper).delete()
        PaperAuthor.objects.bulk_create(
            [
                PaperAuthor(paper=paper, author=authors[name], position=position)
                for position, name in enumerate(record.authors)
            ]
        )
    return outcome


def ingest_records(records: list[PaperRecord], stats: IngestionStats) -> tuple[int, int]:
    """Upsert a batch of records. Returns (created, updated) for this batch."""
    created = updated = 0
    for record in records:
        try:
            outcome = upsert_paper(record)
        except Exception:
            stats.failed += 1
            logger.exception("Failed to store paper %s", record.arxiv_id)
            continue
        if outcome == CREATED:
            created += 1
        elif outcome == UPDATED:
            updated += 1
        else:
            stats.unchanged += 1
    stats.created += created
    stats.updated += updated
    return created, updated


def ingest_from_arxiv(
    categories: list[str],
    max_results: int,
    page_size: int,
    incremental: bool = False,
    client: ArxivClient | None = None,
) -> IngestionStats:
    """
    Fetch papers from arXiv (most recently updated first) and store them.

    With `incremental=True` the run stops at the first page that contains
    nothing new or changed, because older pages cannot contain updates either.
    """
    client = client or ArxivClient()
    stats = IngestionStats()
    task_log = ScheduledTaskLog.objects.create(
        name="arxiv_ingestion",
        json_meta={"categories": categories, "max_results": max_results, "incremental": incremental},
    )
    logger.info(
        "Starting arXiv ingestion: categories=%s max_results=%d page_size=%d incremental=%s",
        categories,
        max_results,
        page_size,
        incremental,
    )
    try:
        for page in client.iter_pages(categories, max_results=max_results, page_size=page_size):
            stats.fetched += len(page.records)
            stats.skipped += page.skipped
            created, updated = ingest_records(page.records, stats)
            logger.info("Page stored: %d created, %d updated (%s)", created, updated, stats)
            if incremental and created == 0 and updated == 0:
                logger.info("Incremental run reached already-known papers; stopping early.")
                break
    except Exception as exc:
        logger.error("arXiv ingestion failed after partial progress: %s (%s)", exc, stats)
        task_log.json_meta["stats"] = stats.as_dict()
        task_log.finish(ScheduledTaskLog.Status.FAILED, f"{exc} ({stats})")
        raise

    task_log.json_meta["stats"] = stats.as_dict()
    task_log.finish(ScheduledTaskLog.Status.SUCCESS, str(stats))
    logger.info("arXiv ingestion finished: %s", stats)
    return stats


def reset_dataset() -> dict[str, int]:
    """Delete every paper, author and category. Embeddings go with their papers (CASCADE)."""
    with transaction.atomic():
        counts = {
            "embeddings": PaperEmbedding.objects.count(),
            "papers": Paper.objects.count(),
            "authors": Author.objects.count(),
            "categories": Category.objects.count(),
        }
        Paper.objects.all().delete()
        Author.objects.all().delete()
        Category.objects.all().delete()
    logger.info("Dataset wiped: %s", counts)
    return counts
