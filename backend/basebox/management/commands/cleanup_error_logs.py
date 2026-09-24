from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from basebox.models.error_log import ErrorLog


class Command(BaseCommand):
    help = 'Delete ErrorLog entries older than N days (default: 30)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=30,
            help='Delete logs older than this many days',
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['days'])
        count, _ = ErrorLog.objects.filter(date_created__lt=cutoff).delete()
        self.stdout.write(f"Deleted {count} error logs older than {options['days']} days.")
