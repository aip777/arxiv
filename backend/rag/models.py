from django.db import models

from basebox.models import TimeStampedModel
from papers.models import Paper


class PaperEmbedding(TimeStampedModel):
    """
    Vector for a paper's title + abstract, stored as L2-normalised float32 bytes.

    `content_hash` and `model` record what the vector was built from, so the
    index can tell when a paper changed (or the model did) and re-embed only those.
    """
    paper = models.OneToOneField(Paper, on_delete=models.CASCADE, primary_key=True,
                                 related_name="embedding")
    embedding = models.BinaryField()
    model = models.CharField(max_length=100, db_index=True)
    content_hash = models.CharField(max_length=64)

    def __str__(self):
        return f"Embedding for {self.paper_id} ({self.model})"
