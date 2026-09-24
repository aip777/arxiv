from django.db import models

from basebox.models import TimeStampedModel


class Category(TimeStampedModel):
    """An arXiv subject class such as `cs.AI` or `stat.ML`."""
    code = models.CharField(max_length=32, unique=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.code


class Author(TimeStampedModel):
    """
    A paper author, identified by normalized name.

    arXiv does not expose author identifiers, so two people sharing a name are
    merged into one row. That is an accepted limitation for this dataset.
    """
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Paper(TimeStampedModel):
    arxiv_id = models.CharField(
        max_length=64, unique=True,
        help_text="arXiv identifier without the version suffix, e.g. 2409.01234",
    )
    version = models.PositiveSmallIntegerField(default=1)
    title = models.TextField()
    abstract = models.TextField()
    primary_category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="primary_papers",
    )
    categories = models.ManyToManyField(Category, related_name="papers")
    authors = models.ManyToManyField(Author, through="PaperAuthor", related_name="papers")
    published = models.DateTimeField(db_index=True)
    updated = models.DateTimeField(db_index=True)
    doi = models.CharField(max_length=255, null=True, blank=True)
    journal_ref = models.TextField(null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    abs_url = models.URLField(max_length=255, blank=True)
    pdf_url = models.URLField(max_length=255, blank=True)
    content_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 of title + abstract; used to detect when the embedding is stale",
    )

    class Meta:
        ordering = ["-published"]

    def __str__(self):
        return f"{self.arxiv_id}: {self.title[:80]}"

    @property
    def embedding_text(self):
        return f"{self.title}\n\n{self.abstract}"


class PaperAuthor(models.Model):
    """Ordered author list for a paper (first author has position 0)."""
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="authorships")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="authorships")
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["paper", "position"]
        constraints = [
            models.UniqueConstraint(fields=["paper", "position"], name="uniq_paper_author_position"),
            models.UniqueConstraint(fields=["paper", "author"], name="uniq_paper_author"),
        ]

    def __str__(self):
        return f"{self.paper_id} #{self.position} {self.author_id}"
