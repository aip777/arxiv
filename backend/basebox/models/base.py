import uuid
from django.db import models
from django.utils import timezone
from basebox.enums.enums import ScheduledTaskLogEnum

class OptimizedQuerySet(models.QuerySet):
    def optimized(self):
        select_fields = []
        prefetch_fields = []

        for field in self.model._meta.get_fields():
            if field.auto_created and not field.concrete:
                # Avoid reverse relations by default
                continue

            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                select_fields.append(field.name)
            elif isinstance(field, models.ManyToManyField):
                prefetch_fields.append(field.name)

        qs = self
        if select_fields:
            qs = qs.select_related(*select_fields)
        if prefetch_fields:
            qs = qs.prefetch_related(*prefetch_fields)

        return qs


class OptimizedManager(models.Manager):
    def get_queryset(self):
        if hasattr(self.model, "get_optimized_queryset"):
            return self.model.get_optimized_queryset()
        return OptimizedQuerySet(self.model, using=self._db).optimized()


class TimeStampedModel(models.Model):
    """Lightweight base for domain tables that only need audit timestamps."""
    date_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    json_meta = models.JSONField(default=dict, blank=True, null=True)
    type = models.CharField(max_length=50, blank=True, null=True)

    objects = OptimizedManager()

    class Meta:
        abstract = True


class ScheduledTaskLog(BaseModel):
    name = models.CharField(max_length=100)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20,choices=ScheduledTaskLogEnum.choices(), default='running')
    message = models.TextField(blank=True, null=True)

    def mark_success(self, message=""):
        self.status = ScheduledTaskLogEnum.SUCCESS.value
        self.end_time = timezone.now()
        self.message = message
        self.save(update_fields=["status", "end_time", "message"])

    def mark_failed(self, message=""):
        self.status = ScheduledTaskLogEnum.FAILED.value
        self.end_time = timezone.now()
        self.message = message
        self.save(update_fields=["status", "end_time", "message"])

    def __str__(self):
        return f"{self.name} ({self.status})"