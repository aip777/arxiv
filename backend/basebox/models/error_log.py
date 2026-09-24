from django.db import models
from basebox.models.base import BaseModel


class ErrorLog(BaseModel):
    level = models.CharField(max_length=10, db_index=True)
    message = models.TextField()
    traceback = models.TextField(blank=True, null=True)
    path = models.CharField(max_length=500, blank=True, null=True)
    method = models.CharField(max_length=10, blank=True, null=True)
    user = models.CharField(max_length=150, blank=True, null=True)
    status_code = models.PositiveSmallIntegerField(blank=True, null=True, db_index=True)

    class Meta:
        ordering = ['-date_created']
        indexes = [
            models.Index(fields=['-date_created']),
            models.Index(fields=['level', '-date_created']),
        ]

    def __str__(self):
        return f"[{self.level}] {self.message[:100]}"
