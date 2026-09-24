"""
Keep the vector index in step with the papers table.

A paper needs (re-)embedding when it has no vector yet, when its title/abstract
changed since the vector was built (content_hash differs), or when the
configured embedding model changed.
"""
import logging

from django.conf import settings
from django.db.models import F

from papers.models import Paper
from rag.models import PaperEmbedding
from rag.services import llm

logger = logging.getLogger(__name__)


def stale_papers():
    return Paper.objects.exclude(
        embedding__model=settings.EMBEDDING_MODEL,
        embedding__content_hash=F("content_hash"),
    )


def sync_index(batch_size: int | None = None) -> int:
    """
    Embed every paper whose vector is missing or stale. Returns how many were embedded.

    Batches are committed as they complete, so a failure part-way keeps the
    finished work and the next run only picks up what is left.
    """
    batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
    pending_ids = list(stale_papers().order_by("pk").values_list("pk", flat=True))
    if not pending_ids:
        logger.info("Vector index is up to date.")
        return 0

    logger.info("Embedding %d papers with %s", len(pending_ids), settings.EMBEDDING_MODEL)
    embedded = 0
    for start in range(0, len(pending_ids), batch_size):
        chunk = pending_ids[start:start + batch_size]
        papers = list(Paper.objects.filter(pk__in=chunk).only("pk", "title", "abstract", "content_hash"))
        vectors = llm.embed_texts([paper.embedding_text for paper in papers])
        PaperEmbedding.objects.bulk_create(
            [
                PaperEmbedding(
                    paper=paper,
                    embedding=vector,
                    model=settings.EMBEDDING_MODEL,
                    content_hash=paper.content_hash,
                )
                for paper, vector in zip(papers, vectors, strict=True)
            ],
            update_conflicts=True,
            unique_fields=["paper"],
            update_fields=["embedding", "model", "content_hash", "last_updated"],
        )
        embedded += len(papers)
        logger.info("Embedded %d/%d papers", embedded, len(pending_ids))
    return embedded
