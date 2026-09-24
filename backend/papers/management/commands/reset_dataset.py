from django.core.management.base import BaseCommand, CommandError

from papers.services.ingestion import reset_dataset


class Command(BaseCommand):
    help = "Delete all papers, authors, categories and embeddings so a fresh import can be run."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirm the wipe without prompting.")

    def handle(self, *args, **options):
        if not options["yes"]:
            answer = input("This permanently deletes the whole dataset. Type 'yes' to continue: ")
            if answer.strip().lower() != "yes":
                raise CommandError("Aborted; nothing was deleted.")

        counts = reset_dataset()
        summary = ", ".join(f"{count} {name}" for name, count in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Deleted {summary}."))
