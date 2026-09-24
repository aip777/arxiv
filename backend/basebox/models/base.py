from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ScheduledTaskLog(TimeStampedModel):
    """One row per run of a background job (e.g. an arXiv ingestion)."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=100, db_index=True)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    message = models.TextField(blank=True, null=True)
    json_meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-start_time"]

    def finish(self, status, message=""):
        self.status = status
        self.end_time = timezone.now()
        self.message = message
        self.save(update_fields=["status", "end_time", "message", "json_meta", "last_updated"])

    def __str__(self):
        return f"{self.name} ({self.status})"
