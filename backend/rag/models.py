from django.db import models
from pgvector.django import HnswIndex, VectorField

from basebox.models import TimeStampedModel
from papers.models import Paper

EMBEDDING_DIMENSIONS = 1536


class PaperEmbedding(TimeStampedModel):
    """
    Vector for a paper's title + abstract.

    `content_hash` and `model` record what the vector was built from, so the
    index can tell when a paper changed (or the model did) and re-embed only those.
    """
    paper = models.OneToOneField(Paper, on_delete=models.CASCADE, primary_key=True,
                                 related_name="embedding")
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS)
    model = models.CharField(max_length=100)
    content_hash = models.CharField(max_length=64)

    class Meta:
        indexes = [
            HnswIndex(
                name="paper_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"Embedding for {self.paper_id} ({self.model})"
