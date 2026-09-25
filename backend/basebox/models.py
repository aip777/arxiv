from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ScheduledTaskLog(TimeStampedModel):
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


class ErrorLog(TimeStampedModel):
    level = models.CharField(max_length=10, db_index=True)
    message = models.TextField()
    traceback = models.TextField(blank=True, null=True)
    path = models.CharField(max_length=500, blank=True, null=True)
    method = models.CharField(max_length=10, blank=True, null=True)
    status_code = models.PositiveSmallIntegerField(blank=True, null=True, db_index=True)

    class Meta:
        ordering = ["-date_created"]
        indexes = [
            models.Index(fields=["-date_created"]),
            models.Index(fields=["level", "-date_created"]),
        ]

    def __str__(self):
        return f"[{self.level}] {self.message[:100]}"
