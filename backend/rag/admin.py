from django.contrib import admin

from rag.models import PaperEmbedding


@admin.register(PaperEmbedding)
class PaperEmbeddingAdmin(admin.ModelAdmin):
    list_display = ["paper", "model", "last_updated"]
    list_filter = ["model"]
    search_fields = ["paper__arxiv_id", "paper__title"]
    raw_id_fields = ["paper"]
    exclude = ["embedding"]
