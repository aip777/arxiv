from django.core.management.base import BaseCommand, CommandError

from rag.services.indexing import stale_papers, sync_index
from rag.services.llm import LLMUnavailable


class Command(BaseCommand):
    help = "Embed papers that have no vector yet or whose title/abstract changed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size", type=int, default=None, help="Texts per embedding request (default: EMBEDDING_BATCH_SIZE)."
        )

    def handle(self, *args, **options):
        pending = stale_papers().count()
        self.stdout.write(f"{pending} papers need embedding.")
        try:
            embedded = sync_index(batch_size=options["batch_size"])
        except LLMUnavailable as exc:
            raise CommandError(f"Could not build the index: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Embedded {embedded} papers."))
