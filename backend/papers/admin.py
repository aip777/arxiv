from django.contrib import admin

from papers.models import Author, Category, Paper, PaperAuthor


class PaperAuthorInline(admin.TabularInline):
    model = PaperAuthor
    extra = 0
    raw_id_fields = ["author"]


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ["arxiv_id", "title", "primary_category", "published", "updated"]
    list_filter = ["primary_category"]
    search_fields = ["arxiv_id", "title", "abstract"]
    date_hierarchy = "published"
    filter_horizontal = ["categories"]
    inlines = [PaperAuthorInline]
    readonly_fields = ["content_hash", "date_created", "last_updated"]
    list_per_page = 50


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    search_fields = ["name"]
    list_per_page = 50


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ["code"]
