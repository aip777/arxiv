from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from papers.services.arxiv_client import ArxivClientError, build_category_query
from papers.services.ingestion import ingest_from_arxiv
from rag.services.indexing import sync_index
from rag.services.llm import LLMUnavailable


class Command(BaseCommand):
    help = (
        "Fetch papers from the arXiv API, upsert them, then refresh the vector index. "
        "Safe to re-run: existing papers are updated in place and only changed ones are re-embedded."
    )

    def add_arguments(self, parser):
        parser.add_argument("--categories", nargs="+", default=None,
                            help="arXiv categories to pull (default: ARXIV_CATEGORIES, e.g. cs.AI cs.LG cs.CL).")
        parser.add_argument("--max-results", type=int, default=1000,
                            help="Maximum number of papers to request (default: 1000).")
        parser.add_argument("--page-size", type=int, default=None,
                            help="Papers per API request (default: ARXIV_PAGE_SIZE, max 2000).")
        parser.add_argument("--incremental", action="store_true",
                            help="Stop at the first page with no new or changed papers.")
        parser.add_argument("--skip-embeddings", action="store_true",
                            help="Only store papers; run `build_index` later to embed them.")

    def handle(self, *args, **options):
        categories = options["categories"] or settings.ARXIV_CATEGORIES
        page_size = options["page_size"] or settings.ARXIV_PAGE_SIZE
        max_results = options["max_results"]
        if max_results < 1:
            raise CommandError("--max-results must be at least 1.")
        if not 1 <= page_size <= 2000:
            raise CommandError("--page-size must be between 1 and 2000.")
        try:
            build_category_query(categories)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Ingesting up to {max_results} papers from {', '.join(categories)} ...")
        try:
            stats = ingest_from_arxiv(
                categories=categories,
                max_results=max_results,
                page_size=page_size,
                incremental=options["incremental"],
            )
        except ArxivClientError as exc:
            raise CommandError(f"Ingestion stopped: {exc}. Papers stored so far are kept; re-run to resume.") from exc
        self.stdout.write(self.style.SUCCESS(f"Ingestion finished: {stats}"))

        if options["skip_embeddings"]:
            self.stdout.write("Skipping embeddings (--skip-embeddings).")
            return
        try:
            embedded = sync_index()
        except LLMUnavailable as exc:
            self.stderr.write(self.style.WARNING(
                f"Papers were stored but the vector index was not updated: {exc} "
                "Run `python manage.py build_index` once the embedding provider is available."
            ))
            return
        self.stdout.write(self.style.SUCCESS(f"Vector index refreshed: {embedded} papers embedded."))
